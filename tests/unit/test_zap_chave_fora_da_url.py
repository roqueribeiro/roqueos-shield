"""A chave da API do ZAP não pode aparecer em URL, log nem /health.

Medido em 2026-11-06 no compose de produção: um 400 do ZAP no poll do spider virou
`zap.poll_failed error="Client error '400 Bad Request' for url
'http://zap:8090/JSON/spider/view/status/?scanId=1&apikey=<a chave>'"` no stdout do
worker. O httpx põe a URL inteira na mensagem de erro; com a chave na query, todo erro
do ZAP vazava o segredo para `docker logs`. A chave agora vai no cabeçalho
`X-ZAP-API-Key` (o ZAP 2.17 aceita: 200 com ela, conexão derrubada sem ela).
"""

from __future__ import annotations

import io
from typing import Any

import httpx
import pytest

from orchestrator.adapters import zap_adapter
from orchestrator.api.routers import health
from orchestrator.standalone import logtee

CHAVE = "chave-do-zap-que-nao-pode-vazar"


def _transporte(vistos: list[httpx.Request], status: int = 400) -> httpx.MockTransport:
    def responder(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        return httpx.Response(status, json={"code": "does_not_exist"})

    return httpx.MockTransport(responder)


async def test_adapter_manda_a_chave_no_cabecalho_e_o_erro_nao_carrega(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vistos: list[httpx.Request] = []
    original = httpx.AsyncClient

    def cliente(*a: Any, **kw: Any) -> httpx.AsyncClient:
        return original(*a, transport=_transporte(vistos), **kw)

    monkeypatch.setattr(zap_adapter.httpx, "AsyncClient", cliente)
    adapter = zap_adapter.ZAPAdapter(base_url="http://zap:8090", api_key=CHAVE)
    with pytest.raises(httpx.HTTPStatusError) as erro:
        await adapter._get("/JSON/spider/view/status/", scanId="1")

    assert vistos, "o adapter não chamou o ZAP"
    pedido = vistos[0]
    assert CHAVE not in str(pedido.url)
    assert "apikey" not in str(pedido.url)
    assert pedido.headers["X-ZAP-API-Key"] == CHAVE
    assert CHAVE not in str(erro.value)


async def test_health_do_zap_nao_poe_a_chave_na_url(monkeypatch: pytest.MonkeyPatch) -> None:
    vistos: list[httpx.Request] = []
    original = httpx.AsyncClient

    def cliente(*a: Any, **kw: Any) -> httpx.AsyncClient:
        return original(*a, transport=_transporte(vistos, status=500), **kw)

    monkeypatch.setattr(health.httpx, "AsyncClient", cliente)
    monkeypatch.setattr(health.settings, "ZAP_API_KEY", CHAVE)
    monkeypatch.setattr(health.settings, "ZAP_BASE_URL", "http://zap:8090")
    r = await health._check_zap()

    assert vistos and CHAVE not in str(vistos[0].url)
    assert vistos[0].headers["X-ZAP-API-Key"] == CHAVE
    assert CHAVE not in str(r)


def test_tee_redige_tambem_o_stdout() -> None:
    out = io.StringIO()
    tee = logtee.Tee("worker", None, out)
    tee.linha(f"GET http://zap:8090/JSON/x/?scanId=1&apikey={CHAVE}\n")
    assert CHAVE not in out.getvalue()
    assert "scanId=1" in out.getvalue()
