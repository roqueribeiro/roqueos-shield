"""Redação de credenciais em log e no stream SSE (Issue #11, item c).

Os adapters logam o argv do scanner (`nmap.start_scan cmd=[...]`), e esse argv carrega
o que o operador passou: `-H "Authorization: Bearer ..."`, `--cookie`, URL com
`user:senha@`. O ring buffer do SSE (`observability.log_processor`) mandava isso para
o navegador de quem abrisse a tela de logs. Este processor roda ANTES do buffer e do
renderer, então nem o stdout nem o SSE recebem o segredo.

Não confundir com `scrubber.py`, que tira PII/PCI do que vai para a LLM.
"""

from __future__ import annotations

import re
from collections.abc import MutableMapping
from typing import Any

REDACTED = "[REDACTED]"

# Flags cujo PRÓXIMO argumento é segredo. Sem `-p` (porta no nmap) nem `-u` (URL no
# nuclei): só o que é inequivocamente credencial.
_FLAGS_SECRETAS = frozenset(
    {
        "-H",
        "--header",
        "-b",
        "--cookie",
        "--user",
        "--password",
        "--pass",
        "--token",
        "--api-key",
        "--apikey",
        "--auth",
        "--bearer",
        "--secret",
    }
)

# Chaves de dicionário (campo de log, header, payload) cujo valor é segredo.
_CHAVES_SECRETAS = frozenset(
    {
        "api_key",
        "apikey",
        "x-api-key",
        "x-api-token",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "set-cookie",
    }
)

_URL_COM_USUARIO = re.compile(r"(?P<esquema>[a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@", re.I)
_BEARER = re.compile(r"\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]{6,}", re.I)
_PAR_CHAVE_VALOR = re.compile(
    r"(?P<chave>\b(?:api[_-]?key|password|passwd|secret|token|access_token|apikey)\b)"
    r"(?P<sep>\s*[=:]\s*)(?P<valor>[^\s&;,'\"]+)",
    re.I,
)
_HEADER = re.compile(r"^(?P<nome>authorization|cookie|x-api-(?:key|token))\s*:\s*.+$", re.I)


def redact_text(texto: str) -> str:
    """Tira credencial de uma string solta (URL, header, `chave=valor`)."""
    if not texto:
        return texto
    m = _HEADER.match(texto.strip())
    if m:
        return f"{m.group('nome')}: {REDACTED}"
    texto = _URL_COM_USUARIO.sub(lambda m: f"{m.group('esquema')}{REDACTED}@", texto)
    texto = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", texto)
    return _PAR_CHAVE_VALOR.sub(lambda m: f"{m.group('chave')}{m.group('sep')}{REDACTED}", texto)


def redact_argv(argv: list[Any] | tuple[Any, ...]) -> list[Any]:
    """argv com o valor depois de cada flag secreta trocado (e `--flag=valor`)."""
    saida: list[Any] = []
    proximo_e_segredo = False
    for arg in argv:
        if proximo_e_segredo:
            saida.append(REDACTED)
            proximo_e_segredo = False
            continue
        if isinstance(arg, str):
            flag, igual, _valor = arg.partition("=")
            if igual and flag in _FLAGS_SECRETAS:
                saida.append(f"{flag}={REDACTED}")
                continue
            if arg in _FLAGS_SECRETAS:
                proximo_e_segredo = True
                saida.append(arg)
                continue
            saida.append(redact_text(arg))
        else:
            saida.append(redact(arg))
    return saida


def redact(valor: Any) -> Any:
    """Redação recursiva: dict por chave, lista como argv, string como texto."""
    if isinstance(valor, str):
        return redact_text(valor)
    if isinstance(valor, dict):
        return {
            k: (REDACTED if str(k).lower() in _CHAVES_SECRETAS and v else redact(v))
            for k, v in valor.items()
        }
    if isinstance(valor, (list, tuple)):
        return redact_argv(valor)
    return valor


def redaction_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> dict[str, Any]:
    """structlog processor: redige todos os campos, menos o nome do evento."""
    evento = event_dict.get("event")
    saida = redact({k: v for k, v in event_dict.items() if k != "event"})
    return {"event": evento, **saida} if "event" in event_dict else saida
