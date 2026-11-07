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
    app.dependency_overrides[deps.get_session] = _sessao
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _setup(c: AsyncClient) -> None:
    r = await c.post("/setup", json={"email": "Admin@X.com", "password": SENHA})
    assert r.status_code == 201, r.text


async def test_primeiro_uso_so_uma_vez(cliente: AsyncClient) -> None:
    assert (await cliente.get("/setup")).json()["needs_setup"] is True
    await _setup(cliente)
    assert "rs_session" in cliente.cookies
    assert (await cliente.get("/setup")).json()["needs_setup"] is False
    r = await cliente.post("/setup", json={"email": "outro@x.com", "password": SENHA})
    assert r.status_code == 410


async def test_setup_recusa_senha_curta(cliente: AsyncClient) -> None:
    r = await cliente.post("/setup", json={"email": "a@x.com", "password": "curta"})
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
