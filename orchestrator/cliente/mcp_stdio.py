"""MCP por stdio (`roqueshield mcp`): para Claude Desktop, Claude Code e Cursor.

Uma mensagem JSON-RPC por linha no stdin, uma resposta por linha no stdout. Log vai
para o stderr, nunca para o stdout, que é do protocolo.

Exemplo para o Claude Code:

    claude mcp add roqueshield -- roqueshield mcp

As ações (disparar scan) só ligam com `ROQUESHIELD_MCP_ACTIONS=1` no ambiente de quem
roda, e mesmo assim cada scan exige a referência da autorização.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx

from orchestrator.cliente.api import Config, ErroDaApi
from orchestrator.cliente.mcp_nucleo import Servidor


class ApiHttp:
    def __init__(self, cfg: Config, cliente: httpx.AsyncClient | None = None) -> None:
        self.http = (
            cliente if cliente is not None else httpx.AsyncClient(base_url=cfg.servidor, timeout=30)
        )
        self.http.headers["X-API-Token"] = cfg.token

    async def _req(self, metodo: str, caminho: str, corpo: Any = None) -> Any:
        r = await self.http.request(metodo, caminho, json=corpo)
        if r.status_code >= 400:
            try:
                detalhe = r.json().get("detail")
            except Exception:  # noqa: BLE001
                detalhe = r.text[:300]
            raise ErroDaApi(r.status_code, detalhe)
        return r.json() if "json" in r.headers.get("content-type", "") else r.text

    async def get(self, caminho: str) -> Any:
        return await self._req("GET", caminho)

    async def post(self, caminho: str, corpo: Any = None) -> Any:
        return await self._req("POST", caminho, corpo or {})


async def _laco(servidor: Servidor) -> None:
    loop = asyncio.get_running_loop()
    leitor = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(leitor), sys.stdin)
    while True:
        linha = await leitor.readline()
        if not linha:
            return
        try:
            msg = json.loads(linha)
        except json.JSONDecodeError:
            resp: dict[str, Any] | None = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "JSON inválido"},
            }
        else:
            resp = await servidor.tratar(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def rodar(cfg: Config) -> None:
    acoes = os.environ.get("ROQUESHIELD_MCP_ACTIONS") == "1"
    print(
        f"roqueshield mcp: {cfg.servidor} (ações {'ligadas' if acoes else 'desligadas'})",
        file=sys.stderr,
    )
    asyncio.run(_laco(Servidor(ApiHttp(cfg), acoes=acoes)))
