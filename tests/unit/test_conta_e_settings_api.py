"""Primeiro uso, login por senha, cookie com CSRF e a API de configuração, pela rota."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from orchestrator import runtime_settings as rs
from orchestrator.api import deps
from orchestrator.config import settings
from orchestrator.main import app

SENHA = "senha-forte-do-admin"
CODIGO = "codigo-de-primeiro-uso"


@pytest.fixture
async def cliente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    fabrica = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _sessao() -> AsyncIterator[AsyncSession]:
        async with fabrica() as s:
            yield s

    for c in rs.TODOS:
        monkeypatch.setattr(settings, c.env, getattr(settings, c.env))
    monkeypatch.setattr(settings, "SECRETS_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "SESSION_SECRET", secrets.token_hex(32))
    monkeypatch.setattr(rs, "_DO_AMBIENTE", frozenset())
    monkeypatch.setattr(settings, "SETUP_CODE", CODIGO)
    from orchestrator.api.routers import conta
    from orchestrator.auth.limite import Freio

    monkeypatch.setattr(conta, "freio", Freio())
    app.dependency_overrides[deps.get_session] = _sessao
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _setup(c: AsyncClient) -> None:
    r = await c.post(
        "/setup", json={"email": "Admin@X.com", "password": SENHA, "setup_code": CODIGO}
    )
    assert r.status_code == 201, r.text


async def test_primeiro_uso_so_uma_vez(cliente: AsyncClient) -> None:
    assert (await cliente.get("/setup")).json()["needs_setup"] is True
    await _setup(cliente)
    assert "rs_session" in cliente.cookies
    assert (await cliente.get("/setup")).json()["needs_setup"] is False
    r = await cliente.post(
        "/setup", json={"email": "outro@x.com", "password": SENHA, "setup_code": CODIGO}
    )
    assert r.status_code == 410


async def test_setup_recusa_senha_curta(cliente: AsyncClient) -> None:
    r = await cliente.post(
        "/setup", json={"email": "a@x.com", "password": "curta", "setup_code": CODIGO}
    )
    assert r.status_code == 422
    assert (await cliente.get("/setup")).json()["needs_setup"] is True


async def test_login_errado_tem_a_mesma_resposta(cliente: AsyncClient) -> None:
    await _setup(cliente)
    cliente.cookies.clear()
    a = await cliente.post(
        "/auth/session", json={"email": "admin@x.com", "password": "errada-errada"}
    )
    b = await cliente.post(
        "/auth/session", json={"email": "ninguem@x.com", "password": "errada-errada"}
    )
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


async def test_login_cookie_e_quem_sou(cliente: AsyncClient) -> None:
    await _setup(cliente)
    cliente.cookies.clear()
    r = await cliente.post("/auth/session", json={"email": "admin@x.com", "password": SENHA})
    assert r.status_code == 200
    eu = await cliente.get("/auth/session")
    assert eu.status_code == 200
    assert eu.json()["role"] == "admin"
    await cliente.delete("/auth/session", headers={"X-RoqueShield": "1"})
    cliente.cookies.clear()
    assert (await cliente.get("/auth/session")).status_code == 401


async def test_escrita_por_cookie_exige_cabecalho_csrf(cliente: AsyncClient) -> None:
    await _setup(cliente)
    sem = await cliente.put("/settings/scope", json={"requireAuthRef": True})
    assert sem.status_code == 403
    com = await cliente.put(
        "/settings/scope", json={"requireAuthRef": True}, headers={"X-RoqueShield": "1"}
    )
    assert com.status_code == 200, com.text
    assert com.json()["requireAuthRef"] is True


async def test_settings_ai_nao_devolve_a_chave(cliente: AsyncClient) -> None:
    await _setup(cliente)
    r = await cliente.put(
        "/settings/ai",
        json={"model": "anthropic/claude-sonnet-4-6", "anthropicKey": "sk-ant-nao-volta"},
        headers={"X-RoqueShield": "1"},
    )
    assert r.status_code == 200, r.text
    assert "sk-ant-nao-volta" not in r.text
    assert r.json()["hasAnthropicKey"] is True
    assert (await cliente.get("/settings/ai")).json()["model"] == "anthropic/claude-sonnet-4-6"


async def test_settings_recusa_campo_desconhecido(cliente: AsyncClient) -> None:
    await _setup(cliente)
    r = await cliente.put("/settings/ai", json={"LLM_MODEL": "x"}, headers={"X-RoqueShield": "1"})
    assert r.status_code == 422


async def test_viewer_nao_le_settings(cliente: AsyncClient) -> None:
    from orchestrator.domain.roles import Role

    app.dependency_overrides[deps.get_principal] = lambda: deps.Principal(
        id="v", email="v@x", role=Role.VIEWER, is_service=False
    )
    assert (await cliente.get("/settings/ai")).status_code == 403
    del app.dependency_overrides[deps.get_principal]


async def test_leituras_da_tela_aceitam_o_cookie(cliente: AsyncClient) -> None:
    # Até o standalone, /ui/api/* só aceitava o APP_TOKEN (o único cliente era o proxy
    # do RoqueOS). A tela standalone entra com o cookie da sessão.
    assert (await cliente.get("/ui/api/scans")).status_code == 401
    await _setup(cliente)
    r = await cliente.get("/ui/api/scans")
    assert r.status_code == 200, r.text
    assert r.json() == []


async def test_token_na_query_so_no_sse(cliente: AsyncClient) -> None:
    r = await cliente.get("/ui/api/scans", params={"token": settings.APP_TOKEN})
    assert r.status_code == 401
    assert "events" in r.json()["detail"]


async def test_ui_aceita_token_de_servico_no_cabecalho(cliente: AsyncClient) -> None:
    r = await cliente.get("/ui/api/scans", headers={"X-API-Token": settings.APP_TOKEN})
    assert r.status_code == 200


async def test_usuarios_com_senha_e_ultimo_admin(cliente: AsyncClient) -> None:
    await _setup(cliente)
    h = {"X-RoqueShield": "1"}
    r = await cliente.post(
        "/users", json={"email": "op@x.com", "role": "operator", "password": "curta"}, headers=h
    )
    assert r.status_code == 422
    r = await cliente.post(
        "/users",
        json={"email": "op@x.com", "role": "operator", "password": "senha-do-operador"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["has_password"] is True and r.json()["api_token"]
    lista = (await cliente.get("/users")).json()
    admin = next(u for u in lista if u["role"] == "admin")
    # o único admin não pode ser desativado nem rebaixado
    assert (await cliente.post(f"/users/{admin['id']}/deactivate", headers=h)).status_code == 409
    r = await cliente.patch(f"/users/{admin['id']}/role", json={"role": "viewer"}, headers=h)
    assert r.status_code == 409
    # o operador entra pela tela com a senha
    cliente.cookies.clear()
    r = await cliente.post(
        "/auth/session", json={"email": "op@x.com", "password": "senha-do-operador"}
    )
    assert r.status_code == 200 and r.json()["role"] == "operator"


async def test_setup_exige_codigo_ou_app_token(cliente: AsyncClient) -> None:
    """Quem alcança a porta antes do dono não vira admin sem acesso ao container."""
    sem = await cliente.post("/setup", json={"email": "a@x.com", "password": SENHA})
    errado = await cliente.post(
        "/setup", json={"email": "a@x.com", "password": SENHA, "setup_code": "chute"}
    )
    assert sem.status_code == errado.status_code == 403
    assert (await cliente.get("/setup")).json()["needs_setup"] is True
    ok = await cliente.post(
        "/setup",
        json={"email": "a@x.com", "password": SENHA},
        headers={"X-API-Token": settings.APP_TOKEN},
    )
    assert ok.status_code == 201, ok.text


async def test_setup_simultaneo_cria_um_admin_so(cliente: AsyncClient) -> None:
    import asyncio

    pedidos = [
        cliente.post(
            "/setup",
            json={"email": f"a{i}@x.com", "password": SENHA, "setup_code": CODIGO},
        )
        for i in range(5)
    ]
    codigos = sorted(r.status_code for r in await asyncio.gather(*pedidos))
    assert codigos.count(201) == 1, codigos
    r = await cliente.get("/users", headers={"X-API-Token": settings.APP_TOKEN})
    assert len(r.json()) == 1


async def test_logout_e_troca_de_senha_derrubam_a_sessao(cliente: AsyncClient) -> None:
    await _setup(cliente)
    copiado = cliente.cookies["rs_session"]
    assert (
        await cliente.delete("/auth/session", headers={"X-RoqueShield": "1"})
    ).status_code == 204
    cliente.cookies.clear()
    cliente.cookies.set("rs_session", copiado)
    assert (await cliente.get("/auth/session")).status_code == 401

    cliente.cookies.clear()
    r = await cliente.post("/auth/session", json={"email": "admin@x.com", "password": SENHA})
    assert r.status_code == 200
    antes = cliente.cookies["rs_session"]
    eu = (await cliente.get("/auth/session")).json()["id"]
    r = await cliente.put(
        f"/users/{eu}/password",
        json={"password": "outra-senha-forte"},
        headers={"X-API-Token": settings.APP_TOKEN},
    )
    assert r.status_code == 200
    cliente.cookies.clear()
    cliente.cookies.set("rs_session", antes)
    assert (await cliente.get("/auth/session")).status_code == 401


async def test_login_trava_depois_de_cinco_falhas(cliente: AsyncClient) -> None:
    await _setup(cliente)
    cliente.cookies.clear()
    for _ in range(5):
        r = await cliente.post(
            "/auth/session", json={"email": "admin@x.com", "password": "errada-1234"}
        )
        assert r.status_code == 401
    # Bloqueado: nem a senha certa entra até a espera passar.
    r = await cliente.post("/auth/session", json={"email": "admin@x.com", "password": SENHA})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


async def test_listar_modelos_nao_manda_chave_guardada_para_endereco_do_pedido(
    cliente: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.standalone import modelos

    vistos: list[dict] = []

    async def falso(c, url, cab):  # type: ignore[no-untyped-def]
        vistos.append({"url": url, **cab})
        return ["m"]

    monkeypatch.setattr(modelos, "_ids", falso)
    monkeypatch.setattr(settings, "LLM_API_KEY", "chave-do-ambiente")
    monkeypatch.setattr(settings, "LLM_API_BASE", "http://lm-local:1234/v1")
    h = {"X-API-Token": settings.APP_TOKEN}
    r = await cliente.post("/settings/ai/models", json={"apiBase": "http://atacante"}, headers=h)
    assert r.status_code == 200
    local = [v for v in vistos if v["url"].startswith("http://atacante")]
    assert local and all("chave-do-ambiente" not in v.get("Authorization", "") for v in local)
    # Com o endereço travado pelo ambiente, nem tenta.
    monkeypatch.setattr(rs, "_DO_AMBIENTE", frozenset({"LLM_API_BASE"}))
    r = await cliente.post("/settings/ai/models", json={"apiBase": "http://atacante"}, headers=h)
    assert r.status_code == 409


async def test_cabecalhos_de_seguranca(cliente: AsyncClient) -> None:
    r = await cliente.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    docs = await cliente.get("/docs")
    assert "Content-Security-Policy" not in docs.headers
