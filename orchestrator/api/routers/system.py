"""Serviços, logs e uso do container standalone (a aba Execução da tela).

Mesma forma das rotas `/pentest/containers` e `/pentest/logs/:service` do
`roqueos-server`. Admin only, como lá: log de scanner pode carregar URL interna do
alvo, e a redação de credencial já aconteceu na entrada (`logtee`).
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from orchestrator.api.deps import Principal, RequireConfigManage
from orchestrator.config import settings
from orchestrator.standalone import logtee, telemetria

router = APIRouter(prefix="/system", tags=["system"])

_SERVICO = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
TETO_DE_LINHAS = 2000
_redis: Any = None


def _cliente() -> Any:
    global _redis
    if _redis is None:
        from redis.asyncio import from_url

        _redis = from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=2)
    return _redis


@router.get("/services")
async def services(_p: Principal = RequireConfigManage) -> dict[str, Any]:
    """Um cartão por processo do container (API, worker, Redis, ZAP), com CPU e memória."""
    return await asyncio.to_thread(telemetria.servicos)


@router.get("/usage")
async def usage(_p: Principal = RequireConfigManage) -> dict[str, Any]:
    """CPU e memória do container inteiro. `disponivel=false` quando não há cgroup."""
    return await asyncio.to_thread(telemetria.uso_do_container)


@router.get("/logs/{service}")
async def logs(
    service: str,
    since: str | None = Query(default=None, description="ISO-8601; só linhas depois disto"),
    tail: int = Query(default=300, ge=1, le=TETO_DE_LINHAS),
    _p: Principal = RequireConfigManage,
) -> dict[str, Any]:
    """As últimas linhas de um serviço. Vazio com `available=false` se o Redis não responde."""
    if not _SERVICO.match(service or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "serviço inválido")
    try:
        brutos = await _cliente().xrevrange(logtee.chave(service), count=tail + 1)
    except Exception:  # noqa: BLE001
        return {
            "service": service,
            "container": service,
            "lines": [],
            "truncated": False,
            "available": False,
        }
    truncated = len(brutos) > tail
    linhas = []
    for _id, campos in reversed(brutos[:tail]):
        ts = (campos.get(b"ts") or b"").decode()
        if since and ts and ts <= since:
            continue
        linhas.append(
            {
                "ts": ts,
                "stream": "stdout",
                "text": (campos.get(b"text") or b"").decode("utf-8", "replace"),
            }
        )
    return {
        "service": service,
        "container": service,
        "lines": linhas,
        "truncated": truncated,
        "available": True,
        "at": datetime.now(UTC).isoformat(),
    }
