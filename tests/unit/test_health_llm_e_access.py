"""Dois defeitos achados ao ligar o RoqueShield central (acemagic-two, 19/11/2026).

1. O health do `llm_local` listava `/models` SEM a chave. O gateway do DGX (proxy
   LiteLLM) exige a chave até para listar, respondia 401, e o painel mostrava a IA
   `down` com a triagem funcionando, ou funcionando com a chave errada sem dizer qual
   das duas era.
2. O CI de fora da rede chega ao shield por um hostname atrás do Cloudflare Access, que
   exige o service token em dois headers. O cliente não sabia mandá-los.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from orchestrator.api.routers import health
from orchestrator.cliente import api as apimod
from orchestrator.config import settings


def _gateway(monkeypatch: pytest.MonkeyPatch, status: int) -> list[httpx.Request]:
    vistas: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        vistas.append(request)
        return httpx.Response(status, json={"data": [{"id": "qwen"}]} if status == 200 else {})

    original = httpx.AsyncClient

    def cliente(*a: Any, **kw: Any) -> httpx.AsyncClient:
        kw["transport"] = httpx.MockTransport(responder)
        return original(*a, **kw)

    monkeypatch.setattr(health.httpx, "AsyncClient", cliente)
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://gw.example/v1")
    return vistas


async def test_health_llm_local_manda_a_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mutação: tirar o `headers=cabecalhos` -> o gateway com auth sai sempre `down`.
    vistas = _gateway(monkeypatch, 200)
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-teste")
    r = await health._check_llm_local()
    assert r["status"] == "ok"
    assert vistas[0].headers["authorization"] == "Bearer sk-teste"


async def test_health_llm_local_diz_que_foi_a_credencial(monkeypatch: pytest.MonkeyPatch) -> None:
    _gateway(monkeypatch, 401)
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-velha")
    r = await health._check_llm_local()
    assert r["status"] == "down"
    assert "credencial" in str(r)


async def test_health_llm_local_sem_chave_nao_inventa_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vistas = _gateway(monkeypatch, 200)
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    await health._check_llm_local()
    assert "authorization" not in vistas[0].headers


def test_access_so_com_os_dois_valores() -> None:
    assert apimod.cabecalhos_de_acesso({}) == {}
    assert apimod.cabecalhos_de_acesso({"CF_ACCESS_CLIENT_ID": "id"}) == {}
    assert apimod.cabecalhos_de_acesso(
        {"CF_ACCESS_CLIENT_ID": " id ", "CF_ACCESS_CLIENT_SECRET": "s"}
    ) == {"CF-Access-Client-Id": "id", "CF-Access-Client-Secret": "s"}


def test_cliente_manda_os_headers_do_access(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mutação: não aplicar `cabecalhos_de_acesso()` no Api -> o CI recebe a tela de
    # login do Cloudflare Access (HTML) no lugar do JSON e quebra sem dizer por quê.
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cid")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "csec")
    vistas: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        vistas.append(request)
        return httpx.Response(200, json={"status": "ok"})

    cfg = apimod.Config("https://shield.example", "tok")
    api = apimod.Api(
        cfg, httpx.Client(base_url=cfg.servidor, transport=httpx.MockTransport(responder))
    )
    api.get("/health")
    h = vistas[0].headers
    assert h["cf-access-client-id"] == "cid"
    assert h["cf-access-client-secret"] == "csec"
    assert h["x-api-token"] == "tok"
