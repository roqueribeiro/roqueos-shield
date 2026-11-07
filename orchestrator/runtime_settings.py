"""Configuração de IA e de escopo editável em runtime.

Até o standalone, essa configuração só existia como variável de ambiente: no RoqueOS
o `roqueos-server` grava as variáveis e recria o container a cada troca de modelo.
Fora do RoqueOS ninguém faz isso, então a tela grava aqui (`app_settings`) e o
processo aplica por cima do `settings` sem reiniciar.

Duas regras:

1. **O ambiente vence.** Variável que veio no ambiente do processo trava o campo: a
   tabela não o sobrescreve, e a API devolve o nome dele em `locked` para a tela
   mostrar "definido pelo ambiente". É o que um ambiente regulado precisa: a política
   vem do deploy, não de quem tem acesso à tela.
2. **Segredo não volta.** Chave de API é gravada cifrada (Fernet com `SECRETS_KEY`) e a
   leitura só diz se existe (`hasApiKey`), nunca o valor.

O formato dos campos é o mesmo do `PentestService` do `roqueos-server`
(`model`, `fallbackModel`, `apiBase`, `labOnly`, `allowlist`, ...), para a tela portada
do RoqueOS falar a mesma língua.

O worker roda em outro processo: ele chama `aplicar()` no começo de cada job, então a
troca vale a partir do próximo scan.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from orchestrator.config import settings
from orchestrator.persistence.models import AppSettingRow


@dataclass(frozen=True)
class Campo:
    chave: str  # nome na API e na tabela
    env: str  # atributo do Settings
    tipo: type  # str | bool | list
    secreto: bool = False


CAMPOS_IA: tuple[Campo, ...] = (
    Campo("model", "LLM_MODEL", str),
    Campo("fallbackModel", "LLM_FALLBACK_MODEL", str),
    Campo("investigationModel", "LLM_INVESTIGATION_MODEL", str),
    Campo("apiBase", "LLM_API_BASE", str),
    Campo("apiKey", "LLM_API_KEY", str, secreto=True),
    Campo("anthropicKey", "ANTHROPIC_API_KEY", str, secreto=True),
    Campo("openaiKey", "OPENAI_API_KEY", str, secreto=True),
    Campo("openrouterKey", "OPENROUTER_API_KEY", str, secreto=True),
)

CAMPOS_ESCOPO: tuple[Campo, ...] = (
    Campo("labOnly", "LAB_ONLY", bool),
    Campo("allowlist", "TARGET_ALLOWLIST", list),
    Campo("requireAuthRef", "REQUIRE_AUTH_REF", bool),
    Campo("allowCloudFallback", "ALLOW_CLOUD_FALLBACK", bool),
)

TODOS = CAMPOS_IA + CAMPOS_ESCOPO
_PREFIXO_CIFRADO = "enc:v1:"

# Fotografia do ambiente no começo do processo: o que veio daqui fica travado.
# Lida uma vez de propósito; `aplicar()` muda o `settings`, não o `os.environ`.
_DO_AMBIENTE: frozenset[str] = frozenset(c.env for c in TODOS if c.env in os.environ)


class SemChaveDeCifra(RuntimeError):
    """Pediram para gravar segredo sem `SECRETS_KEY` configurada."""


# Chave que vem do ambiente prende o endereço para onde ela vai: com o LLM_API_KEY
# injetado pelo deploy e o LLM_API_BASE livre, um admin de tela apontava o endereço
# para um host seu e a chave do deploy ia junto (no listar modelos e em todo scan).
_PRENDE = {"LLM_API_KEY": "LLM_API_BASE"}


def travados(campos: tuple[Campo, ...], do_ambiente: frozenset[str] | None = None) -> list[str]:
    amb = set(_DO_AMBIENTE if do_ambiente is None else do_ambiente)
    amb |= {preso for chave, preso in _PRENDE.items() if chave in amb}
    return [c.chave for c in campos if c.env in amb]


def _fernet():
    from cryptography.fernet import Fernet

    if not settings.SECRETS_KEY:
        raise SemChaveDeCifra(
            "SECRETS_KEY não configurada: sem ela a chave de API não pode ser guardada"
        )
    return Fernet(settings.SECRETS_KEY.encode("ascii"))


def _cifrar(valor: str) -> str:
    return _PREFIXO_CIFRADO + _fernet().encrypt(valor.encode("utf-8")).decode("ascii")


def _decifrar(guardado: str) -> str:
    return _fernet().decrypt(guardado[len(_PREFIXO_CIFRADO) :].encode("ascii")).decode("utf-8")


def _para_settings(campo: Campo, valor: Any) -> Any:
    if campo.tipo is list:
        return json.dumps([str(x) for x in (valor or [])])
    if campo.tipo is bool:
        return bool(valor)
    return "" if valor is None else str(valor)


def _do_settings(campo: Campo) -> Any:
    if campo.tipo is list:
        return settings.target_allowlist
    return getattr(settings, campo.env)


async def _linhas(session: AsyncSession) -> dict[str, AppSettingRow]:
    rows = (await session.exec(select(AppSettingRow))).all()
    return {r.key: r for r in rows}


async def aplicar(session: AsyncSession) -> list[str]:
    """Aplica a tabela por cima do `settings` deste processo. Devolve as chaves aplicadas.

    Campo travado pelo ambiente é pulado. Segredo que não decifra (chave trocada) é
    pulado e não derruba o processo: o scan cai no default e a cobertura diz por quê.
    """
    aplicadas: list[str] = []
    linhas = await _linhas(session)
    for campo in TODOS:
        if campo.env in _DO_AMBIENTE:
            continue
        row = linhas.get(campo.chave)
        if row is None:
            continue
        bruto = json.loads(row.value)
        if campo.secreto and isinstance(bruto, str) and bruto.startswith(_PREFIXO_CIFRADO):
            try:
                bruto = _decifrar(bruto)
            except Exception:  # noqa: BLE001  chave trocada / dado corrompido
                continue
        setattr(settings, campo.env, _para_settings(campo, bruto))
        aplicadas.append(campo.chave)
    return aplicadas


async def gravar(
    session: AsyncSession,
    campos: tuple[Campo, ...],
    valores: dict[str, Any],
    *,
    ator: str | None,
) -> list[str]:
    """Grava os campos presentes em `valores`. Devolve as chaves gravadas.

    Segredo: string vazia apaga; ausente mantém. Campo travado é recusado com
    ValueError (a tela não deveria ter mandado; se mandou, o erro é explícito).
    """
    from datetime import UTC, datetime

    trav = set(travados(campos))
    gravadas: list[str] = []
    linhas = await _linhas(session)
    for campo in campos:
        if campo.chave not in valores:
            continue
        if campo.chave in trav:
            raise ValueError(f"{campo.chave} é definido pelo ambiente e não pode ser trocado aqui")
        valor = valores[campo.chave]
        if campo.secreto:
            valor = "" if valor is None else str(valor)
            guardar: Any = _cifrar(valor) if valor else ""
        elif campo.tipo is list:
            guardar = [str(x).strip() for x in (valor or []) if str(x).strip()]
        elif campo.tipo is bool:
            guardar = bool(valor)
        else:
            guardar = "" if valor is None else str(valor).strip()
        row = linhas.get(campo.chave)
        if row is None:
            row = AppSettingRow(key=campo.chave, value="")
        row.value = json.dumps(guardar)
        row.updated_at = datetime.now(UTC)
        row.updated_by = ator
        session.add(row)
        gravadas.append(campo.chave)
    await session.flush()
    await aplicar(session)
    return gravadas


def ia_mascarada() -> dict[str, Any]:
    """A config de IA efetiva, sem segredo. Forma do `PentestAiConfigMasked` do server."""
    base = settings.LLM_API_BASE or ""
    local = any(
        h in base
        for h in (
            "localhost",
            "127.0.0.1",
            "host.docker.internal",
            "ollama",
            "lmstudio",
            "lm-studio",
        )
    )
    return {
        "model": settings.LLM_MODEL,
        "fallbackModel": settings.LLM_FALLBACK_MODEL,
        "investigationModel": settings.LLM_INVESTIGATION_MODEL,
        "apiBase": base,
        "hasApiKey": bool(settings.LLM_API_KEY),
        "hasAnthropicKey": bool(settings.ANTHROPIC_API_KEY),
        "hasOpenaiKey": bool(settings.OPENAI_API_KEY),
        "hasOpenrouterKey": bool(settings.OPENROUTER_API_KEY),
        "isLocal": bool(base) and local,
        "locked": travados(CAMPOS_IA),
    }


def escopo() -> dict[str, Any]:
    """O escopo efetivo. Forma do `PentestScopeConfig` do server, mais `locked`."""
    return {
        "labOnly": bool(settings.LAB_ONLY),
        "allowlist": settings.target_allowlist,
        "requireAuthRef": bool(settings.REQUIRE_AUTH_REF),
        "allowCloudFallback": bool(settings.ALLOW_CLOUD_FALLBACK),
        "locked": travados(CAMPOS_ESCOPO),
    }
