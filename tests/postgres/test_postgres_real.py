"""O que só o Postgres prova (migrations, triggers, FKs e concorrência de verdade).

A suíte padrão roda em SQLite, que cria o schema direto dos modelos, não força FK, não
tem os triggers append-only (são Postgres-only) e serializa as escritas. Tudo o que é
garantia de produção nesta lista passava verde sem nunca ter rodado:

- o schema que as migrations geram bate com os modelos (`alembic check`);
- `audit_log` e `evidence_snapshots` recusam UPDATE e DELETE (trigger);
- o DELETE de scan passa com ativos e evidência apontando para ele (FK forçada);
- duas decisões simultâneas na mesma pendência: só uma ganha;
- dois scans simultâneos registrando o mesmo ativo novo: nenhum derruba o outro.

Roda só com `ROQUESHIELD_PG_TEST_URL` (o job "Postgres real" do CI sobe o serviço):

    ROQUESHIELD_PG_TEST_URL=postgresql+asyncpg://cai:cai@127.0.0.1:55432/cai \\
        uv run pytest tests/postgres -q
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from orchestrator.approvals import service as aprovacoes
from orchestrator.config import settings
from orchestrator.domain.assets import asset_key, registrar_ativos
from orchestrator.domain.schemas import AssetType, Confidence, Finding, Severity, Target
from orchestrator.persistence.models import (
    AssetObservationRow,
    AssetRow,
    AuditLogRow,
    CommandApprovalRow,
    CommandApprovalStatus,
    EvidenceSnapshotRow,
    ScanRow,
    TargetRow,
)

PG_URL = os.environ.get("ROQUESHIELD_PG_TEST_URL", "")
RAIZ = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not PG_URL, reason="sem ROQUESHIELD_PG_TEST_URL: estes testes exigem um Postgres real"
)


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATABASE_URL": PG_URL}
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=RAIZ,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module", autouse=True)
def _migrado() -> None:
    feito = _alembic("upgrade", "head")
    assert feito.returncode == 0, feito.stderr[-2000:]


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    # Um engine por teste: conexões do asyncpg ficam presas ao event loop que as criou.
    eng = create_async_engine(PG_URL)
    try:
        yield eng
    finally:
        await eng.dispose()


def _fabrica(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# --------------------------------------------------------------- schema = modelos


def test_migrations_batem_com_os_modelos() -> None:
    feito = _alembic("check")
    assert feito.returncode == 0, (
        "o schema que as migrations geram diverge dos modelos (o standalone usa create_all, "
        "a produção usa as migrations: os dois bancos ficam diferentes):\n"
        + (feito.stdout + feito.stderr)[-3000:]
    )


# ------------------------------------------------------------ triggers append-only


async def _linha_de_auditoria(engine: AsyncEngine) -> uuid.UUID:
    async with _fabrica(engine)() as s:
        linha = AuditLogRow(action="teste.pg", actor="pg@x")
        s.add(linha)
        await s.commit()
        return linha.id


@pytest.mark.parametrize("sql", ["UPDATE audit_log SET actor = 'x'", "DELETE FROM audit_log"])
async def test_audit_log_recusa_update_e_delete(engine: AsyncEngine, sql: str) -> None:
    alvo = await _linha_de_auditoria(engine)
    async with engine.connect() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            await conn.execute(text(f"{sql} WHERE id = :i"), {"i": alvo})


async def _snapshot(engine: AsyncEngine, scan_id: uuid.UUID | None = None) -> uuid.UUID:
    async with _fabrica(engine)() as s:
        snap = EvidenceSnapshotRow(sha256=uuid.uuid4().hex, original_sha256="orig", scan_id=scan_id)
        s.add(snap)
        await s.commit()
        return snap.id


@pytest.mark.parametrize(
    "sql", ["UPDATE evidence_snapshots SET size_bytes = 1", "DELETE FROM evidence_snapshots"]
)
async def test_evidence_snapshots_recusa_update_e_delete(engine: AsyncEngine, sql: str) -> None:
    alvo = await _snapshot(engine)
    async with engine.connect() as conn:
        with pytest.raises(DBAPIError, match="append-only"):
            await conn.execute(text(f"{sql} WHERE id = :i"), {"i": alvo})


# ------------------------------------------------------- DELETE de scan com as FKs


async def test_delete_de_scan_passa_com_ativos_e_evidencia(engine: AsyncEngine) -> None:
    from orchestrator.api import deps
    from orchestrator.domain.roles import Role
    from orchestrator.main import app
    from orchestrator.persistence.db import get_session

    fabrica = _fabrica(engine)
    scan_id, asset_id = uuid.uuid4(), uuid.uuid4()
    async with fabrica() as s:
        alvo = TargetRow(asset_type="host", value=f"pg-{scan_id}.test")
        s.add(alvo)
        await s.flush()
        s.add(ScanRow(id=scan_id, target_id=alvo.id, state="done"))
        await s.flush()
        s.add(
            AssetRow(
                id=asset_id,
                asset_key=uuid.uuid4().hex[:32],
                asset_type="host",
                value=f"pg-{scan_id}.test",
                last_scan_id=scan_id,
            )
        )
        await s.flush()
        s.add(AssetObservationRow(asset_id=asset_id, scan_id=scan_id, source_tool="nmap"))
        s.add(EvidenceSnapshotRow(sha256=uuid.uuid4().hex, original_sha256="o", scan_id=scan_id))
        await s.commit()

    async def _sessao_pg() -> AsyncIterator[AsyncSession]:
        async with fabrica() as s:
            yield s

    app.dependency_overrides[get_session] = _sessao_pg
    app.dependency_overrides[deps.get_principal] = lambda: deps.Principal(
        id="u1", email="admin@x", role=Role.ADMIN, is_service=True
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.delete(f"/scans/{scan_id}")
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(deps.get_principal, None)

    assert resp.status_code == 204, resp.text
    async with fabrica() as s:
        assert await s.get(ScanRow, scan_id) is None
        ativo = await s.get(AssetRow, asset_id)
        assert ativo is not None and ativo.last_scan_id is None
        restos = (
            await s.exec(
                select(EvidenceSnapshotRow).where(col(EvidenceSnapshotRow.scan_id) == scan_id)
            )
        ).all()
        assert len(restos) == 1  # a evidência imutável sobrevive ao scan


# ------------------------------------------------------- concorrência de verdade


async def test_decisoes_simultaneas_so_uma_ganha(engine: AsyncEngine) -> None:
    fabrica = _fabrica(engine)
    async with fabrica() as s:
        aid = (await aprovacoes.criar_pendencia(s, command="nmap alvo", proposed_by="op@x")).id

    async def decidir(aprovar: bool, quem: str) -> str:
        async with fabrica() as s:
            try:
                linha = await aprovacoes.decidir(s, aid, aprovar=aprovar, decided_by=quem)
                return linha.status
            except aprovacoes.JaDecidida:
                return "perdeu"

    # Várias rodadas: uma corrida que só às vezes acontece também tem de ser pega.
    resultados = await asyncio.gather(*[decidir(i % 2 == 0, f"adm{i}@x") for i in range(8)])
    vencedores = [r for r in resultados if r != "perdeu"]
    assert len(vencedores) == 1, resultados

    async with fabrica() as s:
        final = await s.get(CommandApprovalRow, aid)
        assert final is not None and final.status == vencedores[0]
        decisoes = (
            await s.exec(
                select(AuditLogRow)
                .where(col(AuditLogRow.resource_id) == aid)
                .where(col(AuditLogRow.action).in_(["command.approve", "command.deny"]))
            )
        ).all()
        assert len(decisoes) == 1  # a trilha registra só a decisão que valeu


async def test_aprovar_nao_passa_depois_do_prazo(engine: AsyncEngine) -> None:
    fabrica = _fabrica(engine)
    async with fabrica() as s:
        linha = await aprovacoes.criar_pendencia(s, command="nmap alvo", proposed_by="op@x")
        aid = linha.id
    async with engine.begin() as conn:  # vence a pendência no próprio banco
        await conn.execute(
            text("UPDATE command_approvals SET expires_at = :t WHERE id = :i"),
            {"t": datetime.now(UTC) - timedelta(seconds=5), "i": aid},
        )
    async with fabrica() as s:
        with pytest.raises(aprovacoes.Expirada):
            await aprovacoes.decidir(s, aid, aprovar=True, decided_by="adm@x")
        assert await aprovacoes.esta_aprovado(s, aid) is False
    async with fabrica() as s:
        final = await s.get(CommandApprovalRow, aid)
        assert final is not None and final.status == CommandApprovalStatus.EXPIRED.value


async def test_ativo_novo_em_scans_simultaneos_nao_derruba_nenhum(engine: AsyncEngine) -> None:
    fabrica = _fabrica(engine)
    host = f"corrida-{uuid.uuid4().hex[:8]}.test"
    alvo = Target(asset_type=AssetType.HOST, value=host)

    async def scan() -> uuid.UUID:
        scan_id = uuid.uuid4()
        async with fabrica() as s:
            t = TargetRow(asset_type="host", value=f"{host}-{scan_id}")
            s.add(t)
            await s.flush()
            s.add(ScanRow(id=scan_id, target_id=t.id, state="running"))
            await s.flush()
            f = Finding(
                scan_id=scan_id,
                target=Target(asset_type=AssetType.PORT, value=f"{host}:443/tcp"),
                source_tool="nmap",
                source_rule_id="port-443-tcp",
                title="Open port 443/tcp",
                description="aberta",
                severity=Severity.INFO,
                confidence=Confidence.CERTAIN,
            )
            await registrar_ativos(s, scan_id, alvo, [f], scanners_ran=["nmap"])
            await s.commit()
            assert f.asset_id is not None
            return f.asset_id

    ids = await asyncio.gather(*[scan() for _ in range(6)])
    assert len(set(ids)) == 1, "cada scan criou o seu próprio ativo para a mesma porta"
    async with fabrica() as s:
        linhas = (
            await s.exec(
                select(AssetRow).where(
                    col(AssetRow.asset_key) == asset_key("port", f"{host}:443/tcp")
                )
            )
        ).all()
        assert len(linhas) == 1
        obs = (
            await s.exec(
                select(AssetObservationRow).where(col(AssetObservationRow.asset_id) == ids[0])
            )
        ).all()
        assert len(obs) == 6  # uma observação por scan, nenhuma perdida na corrida


def test_settings_aponta_para_o_postgres_so_neste_modulo() -> None:
    # Sanidade: a suíte padrão continua em SQLite; este módulo fala com o Postgres por
    # engine próprio, sem mexer no settings global.
    assert settings.DATABASE_URL.startswith("sqlite")
