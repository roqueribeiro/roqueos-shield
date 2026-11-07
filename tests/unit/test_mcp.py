"""O servidor MCP: protocolo, as duas regras (sem vazio silencioso, ação com
autorização) e o transporte HTTP pela rota com o RBAC de sempre."""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.cliente.mcp_nucleo import Servidor


class _ApiFalsa:
    def __init__(self, scan: dict[str, Any]) -> None:
        self.scan = scan
        self.posts: list[tuple[str, Any]] = []

    async def get(self, caminho: str) -> Any:
        if caminho.startswith("/ui/api/scans/"):
            return self.scan
        if caminho.startswith("/ui/api/findings"):
            return [{"title": "XSS", "severity": "high"}]
        if caminho.endswith("/ai-bundle"):
            return {"schema_version": "1.0.0", "findings": []}
        if caminho == "/targets":
            return []
        return []

    async def post(self, caminho: str, corpo: Any = None) -> Any:
        self.posts.append((caminho, corpo))
        return {"id": "t1"} if caminho == "/targets" else {"id": "s9", "state": "pending"}


def _ok() -> dict[str, Any]:
    return {"state": "done", "coverage_complete": True, "scanners_skipped": {}}


async def _chamar(s: Servidor, nome: str, args: dict[str, Any]) -> dict[str, Any]:
    r = await s.tratar(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": nome, "arguments": args},
        }
    )
    assert r is not None
    return r["result"]


async def test_initialize_e_lista() -> None:
    s = Servidor(_ApiFalsa(_ok()), versao="0.5.0")
    r = await s.tratar(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
    )
    assert r is not None and r["result"]["protocolVersion"] == "2025-06-18"
    assert r["result"]["serverInfo"] == {"name": "roqueshield", "version": "0.5.0"}
    assert await s.tratar({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    lista = await s.tratar({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    nomes = {t["name"] for t in lista["result"]["tools"]}  # type: ignore[index]
    assert "get_findings" in nomes and "start_scan" not in nomes


async def test_achados_de_scan_completo() -> None:
    r = await _chamar(Servidor(_ApiFalsa(_ok())), "get_findings", {"scan_id": "x"})
    assert r["isError"] is False
    assert json.loads(r["content"][0]["text"])[0]["title"] == "XSS"


@pytest.mark.parametrize(
    "scan",
    [
        {
            "state": "done",
            "coverage_complete": False,
            "scanners_skipped": {"nuclei": "sem templates"},
        },
        {"state": "failed", "coverage_complete": False},
        {"state": "running"},
    ],
)
async def test_scan_incompleto_e_erro_nunca_vazio(scan: dict[str, Any]) -> None:
    s = Servidor(_ApiFalsa(scan))
    for nome in ("get_findings", "get_ai_bundle"):
        r = await _chamar(s, nome, {"scan_id": "x"})
        assert r["isError"] is True, nome
        assert "erro" in json.loads(r["content"][0]["text"])


async def test_acao_desligada_nao_existe() -> None:
    s = Servidor(_ApiFalsa(_ok()), acoes=False)
    r = await s.tratar(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "start_scan", "arguments": {}},
        }
    )
    assert r is not None and r["error"]["code"] == -32602


async def test_acao_exige_autorizacao() -> None:
    api = _ApiFalsa(_ok())
    s = Servidor(api, acoes=True)
    r = await _chamar(s, "start_scan", {"target": "http://a", "authorization_ref": ""})
    assert r["isError"] is True and api.posts == []
    r = await _chamar(s, "start_scan", {"target": "http://a", "authorization_ref": "CHG-42"})
    assert r["isError"] is False
    assert api.posts[1] == (
        "/scans",
        {"target_id": "t1", "profile": "web", "authorization_ref": "CHG-42"},
    )


async def test_metodo_desconhecido() -> None:
    r = await Servidor(_ApiFalsa(_ok())).tratar(
        {"jsonrpc": "2.0", "id": 9, "method": "resources/list"}
    )
    assert r is not None and r["error"]["code"] == -32601


async def test_rota_http_exige_credencial_e_responde() -> None:
    from orchestrator.config import settings
    from orchestrator.main import app
    from orchestrator.persistence.db import init_db

    await init_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        sem = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        assert sem.status_code == 401
        com = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"X-API-Token": settings.APP_TOKEN},
        )
        assert com.status_code == 200
        assert any(t["name"] == "list_scans" for t in com.json()["result"]["tools"])
        lista = await c.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_scans", "arguments": {}},
            },
            headers={"X-API-Token": settings.APP_TOKEN},
        )
        assert lista.json()["result"]["isError"] is False, lista.json()
