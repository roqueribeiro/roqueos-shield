"""Lista os modelos de IA que as chaves configuradas realmente alcançam.

Porta do `listAiModels` do `roqueos-server`: o shield chama o `/models` de cada
provedor do lado do servidor, então a chave nunca vai para o navegador. A chave
mandada no corpo vence a guardada (deixa a tela listar antes de salvar). Provedor que
falha cai numa lista curta escrita à mão e entra em `errors`, para a tela dizer que
aquela lista não veio do provedor.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

from orchestrator.config import settings

log = structlog.get_logger(__name__)

CURADOS: dict[str, list[dict[str, str]]] = {
    "anthropic": [
        {"id": "anthropic/claude-opus-4-7", "label": "claude-opus-4-7"},
        {"id": "anthropic/claude-sonnet-4-6", "label": "claude-sonnet-4-6"},
        {"id": "anthropic/claude-haiku-4-5-20251001", "label": "claude-haiku-4-5"},
    ],
    "openai": [
        {"id": "openai/gpt-4o", "label": "gpt-4o"},
        {"id": "openai/gpt-4o-mini", "label": "gpt-4o-mini"},
    ],
    "openrouter": [],
    "local": [],
}
_CHAT_OPENAI = re.compile(r"^(gpt-|o\d|chatgpt)", re.IGNORECASE)


async def _ids(cliente: httpx.AsyncClient, url: str, headers: dict[str, str]) -> list[str]:
    r = await cliente.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    corpo: Any = r.json()
    dados = corpo.get("data") if isinstance(corpo, dict) else None
    if not isinstance(dados, list):
        dados = corpo.get("models") if isinstance(corpo, dict) else []
    saida: list[str] = []
    for m in dados or []:
        if isinstance(m, dict):
            v = m.get("id") or m.get("name")
            if isinstance(v, str) and v:
                saida.append(v)
    return saida


async def listar(
    fornecidas: dict[str, str] | None = None, cliente: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    f = fornecidas or {}
    anthropic = f.get("anthropicKey") or settings.ANTHROPIC_API_KEY
    openai = f.get("openaiKey") or settings.OPENAI_API_KEY
    openrouter = f.get("openrouterKey") or settings.OPENROUTER_API_KEY
    if f.get("apiBase") is not None:
        # Endereço vindo do pedido leva só a chave vinda do pedido. Com a guardada, quem
        # pudesse chamar esta rota mandava a LLM_API_KEY do ambiente para um host seu.
        base = f.get("apiBase") or ""
        chave_local = f.get("apiKey") or "local"
    else:
        base = settings.LLM_API_BASE or ""
        chave_local = f.get("apiKey") or settings.LLM_API_KEY or "local"

    grupos: list[dict[str, Any]] = []
    erros: list[str] = []
    proprio = cliente is None
    c = cliente or httpx.AsyncClient()
    try:

        async def add(prov: str, rotulo: str, coleta: Any) -> None:
            try:
                modelos = await coleta()
                if not modelos:
                    raise ValueError("lista vazia")
                grupos.append({"provider": prov, "label": rotulo, "live": True, "models": modelos})
            except Exception as e:  # noqa: BLE001  qualquer falha do provedor vira fallback declarado
                log.warning("settings.listar_modelos_falhou", provider=prov, error=type(e).__name__)
                erros.append(prov)
                if CURADOS.get(prov):
                    grupos.append(
                        {"provider": prov, "label": rotulo, "live": False, "models": CURADOS[prov]}
                    )

        if anthropic:

            async def _anthropic() -> list[dict[str, str]]:
                ids = await _ids(
                    c,
                    "https://api.anthropic.com/v1/models",
                    {"x-api-key": anthropic, "anthropic-version": "2023-06-01"},
                )
                return [{"id": f"anthropic/{i}", "label": i} for i in ids]

            await add("anthropic", "Anthropic", _anthropic)
        if openai:

            async def _openai() -> list[dict[str, str]]:
                ids = await _ids(
                    c, "https://api.openai.com/v1/models", {"Authorization": f"Bearer {openai}"}
                )
                return [
                    {"id": f"openai/{i}", "label": i} for i in sorted(ids) if _CHAT_OPENAI.match(i)
                ]

            await add("openai", "OpenAI", _openai)
        if openrouter:

            async def _openrouter() -> list[dict[str, str]]:
                ids = await _ids(
                    c,
                    "https://openrouter.ai/api/v1/models",
                    {"Authorization": f"Bearer {openrouter}"},
                )
                return [{"id": f"openrouter/{i}", "label": i} for i in ids]

            await add("openrouter", "OpenRouter", _openrouter)
        if base:

            async def _local() -> list[dict[str, str]]:
                ids = await _ids(
                    c, f"{base.rstrip('/')}/models", {"Authorization": f"Bearer {chave_local}"}
                )
                return [{"id": i, "label": i} for i in ids]

            await add("local", "Local (LM Studio / Ollama)", _local)
    finally:
        if proprio:
            await c.aclose()
    return {"groups": grupos, "errors": erros}
