"""MCP por HTTP em `/mcp` (transporte Streamable HTTP, respostas em JSON).

Para cliente MCP que fala com o shield pela rede. Autentica como o resto da API
(`X-API-Token` de usuário, ou `Authorization: Bearer`), e cada ferramenta chama a API
REST por dentro do mesmo processo (sem rede), repassando a credencial de quem chamou:
o RBAC é o de sempre. Ações (disparar scan) só com `MCP_ALLOW_ACTIONS=true`.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from orchestrator.api.deps import PrincipalDep
from orchestrator.cliente.api import Config
from orchestrator.cliente.mcp_nucleo import Servidor
from orchestrator.cliente.mcp_stdio import ApiHttp
from orchestrator.config import settings

router = APIRouter(tags=["mcp"])


@router.post("/mcp")
async def mcp_http(request: Request, _p: PrincipalDep) -> Response:
    """Uma mensagem JSON-RPC do protocolo MCP (initialize, tools/list, tools/call…)."""
    from orchestrator.main import app

    try:
        msg = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON inválido"}}
        )
    if not isinstance(msg, dict):
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "lote não suportado"},
            },
        )
    cabecalhos = {
        k: v for k, v in request.headers.items() if k.lower() in ("x-api-token", "authorization")
    }
    interno = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://interno", headers=cabecalhos
    )
    async with interno:
        api = ApiHttp(Config("http://interno", cabecalhos.get("x-api-token", "")), interno)
        if "x-api-token" not in cabecalhos:
            api.http.headers.pop("X-API-Token", None)
        resp: dict[str, Any] | None = await Servidor(
            api, acoes=bool(settings.MCP_ALLOW_ACTIONS), versao=app.version
        ).tratar(msg)
    if resp is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return JSONResponse(resp)


@router.get("/mcp", include_in_schema=False)
async def mcp_sem_stream() -> Response:
    # Este servidor não abre stream SSE do servidor para o cliente (não manda
    # notificação espontânea). O transporte prevê 405 nesse caso.
    return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED)
