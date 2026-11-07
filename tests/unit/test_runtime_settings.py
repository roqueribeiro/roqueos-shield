"""Configuração em runtime: o ambiente trava, o segredo vai cifrado, e o efeito é imediato."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from orchestrator import runtime_settings as rs
from orchestrator.config import settings
from orchestrator.persistence.models import AppSettingRow


@pytest.fixture
async def sessao(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rs.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    fabrica = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrica() as s:
        yield s
    await engine.dispose()


@pytest.fixture(autouse=True)
def _settings_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    # Cada teste começa com o settings que tinha, e sem nada travado pelo ambiente.
    for c in rs.TODOS:
        monkeypatch.setattr(settings, c.env, getattr(settings, c.env))
    monkeypatch.setattr(settings, "SECRETS_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(rs, "_DO_AMBIENTE", frozenset())


async def test_gravar_aplica_na_hora(sessao: AsyncSession) -> None:
    await rs.gravar(sessao, rs.CAMPOS_IA, {"model": "openai/gpt-4o"}, ator="a@x")
    assert settings.LLM_MODEL == "openai/gpt-4o"
    assert rs.ia_mascarada()["model"] == "openai/gpt-4o"


async def test_chave_vai_cifrada_e_nunca_volta(sessao: AsyncSession) -> None:
    await rs.gravar(sessao, rs.CAMPOS_IA, {"anthropicKey": "sk-ant-segredo-xyz"}, ator="a@x")
    row = (
        await sessao.exec(select(AppSettingRow).where(AppSettingRow.key == "anthropicKey"))
    ).one()
    assert "sk-ant-segredo-xyz" not in row.value
    assert json.loads(row.value).startswith("enc:v1:")
    assert settings.ANTHROPIC_API_KEY == "sk-ant-segredo-xyz"
    masc = rs.ia_mascarada()
    assert masc["hasAnthropicKey"] is True
    assert "sk-ant-segredo-xyz" not in json.dumps(masc)


async def test_chave_vazia_apaga(sessao: AsyncSession) -> None:
    await rs.gravar(sessao, rs.CAMPOS_IA, {"openaiKey": "sk-1"}, ator=None)
    await rs.gravar(sessao, rs.CAMPOS_IA, {"openaiKey": ""}, ator=None)
    assert settings.OPENAI_API_KEY == ""
    assert rs.ia_mascarada()["hasOpenaiKey"] is False


async def test_ambiente_trava_o_campo(
    sessao: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rs, "_DO_AMBIENTE", frozenset({"LAB_ONLY"}))
    with pytest.raises(ValueError, match="ambiente"):
        await rs.gravar(sessao, rs.CAMPOS_ESCOPO, {"labOnly": False}, ator=None)
    assert "labOnly" in rs.escopo()["locked"]


async def test_aplicar_pula_campo_travado(
    sessao: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessao.add(AppSettingRow(key="model", value=json.dumps("da-tabela/x")))
    await sessao.flush()
    monkeypatch.setattr(settings, "LLM_MODEL", "do-ambiente/y")
    monkeypatch.setattr(rs, "_DO_AMBIENTE", frozenset({"LLM_MODEL"}))
    await rs.aplicar(sessao)
    assert settings.LLM_MODEL == "do-ambiente/y"


async def test_escopo_lista_e_bool(sessao: AsyncSession) -> None:
    await rs.gravar(
        sessao,
        rs.CAMPOS_ESCOPO,
        {"allowlist": [" app.x.com ", "", "10.0.0.0/8"], "requireAuthRef": True},
        ator=None,
    )
    e = rs.escopo()
    assert e["allowlist"] == ["app.x.com", "10.0.0.0/8"]
    assert e["requireAuthRef"] is True


async def test_sem_chave_de_cifra_recusa_segredo(
    sessao: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SECRETS_KEY", "")
    with pytest.raises(rs.SemChaveDeCifra):
        await rs.gravar(sessao, rs.CAMPOS_IA, {"apiKey": "x"}, ator=None)


async def test_chave_trocada_nao_derruba(
    sessao: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await rs.gravar(sessao, rs.CAMPOS_IA, {"apiKey": "local-1"}, ator=None)
    monkeypatch.setattr(settings, "SECRETS_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    aplicadas = await rs.aplicar(sessao)
    assert "apiKey" not in aplicadas
    assert settings.LLM_API_KEY == ""
