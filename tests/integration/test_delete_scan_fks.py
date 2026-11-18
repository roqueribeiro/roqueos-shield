"""DELETE /scans/{id} convive com as tabelas novas (Frentes A e C).

Bug pego na revisão: `asset_observations.scan_id`, `assets.last_scan_id` e
`evidence_snapshots.scan_id` passaram a apontar para o scan. A rota de delete só
removia findings e AIRuns, então no Postgres a FK abortava o delete — e um scan com
evidência nunca sairia, porque o trigger append-only recusa até o SET NULL.

O conserto: a rota limpa o vínculo dos ativos (sem apagar o ativo, que persiste entre
scans) e o `evidence_snapshots` perdeu a FK (é imutável e sobrevive ao scan). Aqui a
suíte roda em SQLite, que não força FK, então o teste afirma o COMPORTAMENTO: o delete
passa, a observação some, o `last_scan_id` zera, e o ativo e a evidência sobrevivem.
"""

from __future__ import annotations

import uuid

from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select

from orchestrator.api import deps
from orchestrator.domain.roles import Role
from orchestrator.main import app
from orchestrator.persistence.db import init_db, session
from orchestrator.persistence.models import (
    AssetObservationRow,
    AssetRow,
    EvidenceSnapshotRow,
    ScanRow,
    TargetRow,
)


async def test_delete_scan_com_ativos_e_evidencia() -> None:
    await init_db()
    scan_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    async with session() as s:
        alvo = TargetRow(asset_type="host", value=f"alvo-{scan_id}.test")
        s.add(alvo)
        await s.flush()
        s.add(ScanRow(id=scan_id, target_id=alvo.id, state="done"))
        s.add(
            AssetRow(
                id=asset_id,
                asset_key=f"k-{scan_id.hex[:20]}",
                asset_type="host",
                value=f"alvo-{scan_id}.test",
                last_scan_id=scan_id,
            )
        )
        s.add(AssetObservationRow(asset_id=asset_id, scan_id=scan_id, source_tool="nmap"))
        s.add(
            EvidenceSnapshotRow(
                sha256=f"sha-{scan_id.hex}", original_sha256="orig", scan_id=scan_id
            )
        )
        await s.commit()

    app.dependency_overrides[deps.get_principal] = lambda: deps.Principal(
        id="u1", email="admin@x", role=Role.ADMIN, is_service=True
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            resp = await client.delete(f"/scans/{scan_id}")
    finally:
        app.dependency_overrides.pop(deps.get_principal, None)

    assert resp.status_code == 204, resp.text

    async with session() as s:
        assert await s.get(ScanRow, scan_id) is None  # scan removido
        ativo = await s.get(AssetRow, asset_id)
        assert ativo is not None  # o ativo PERSISTE entre scans
        assert ativo.last_scan_id is None  # mas o vínculo com este scan zerou
        obs = (
            await s.exec(
                select(AssetObservationRow).where(col(AssetObservationRow.scan_id) == scan_id)
            )
        ).all()
        assert obs == []  # observação do scan removida
        ev = (
            await s.exec(
                select(EvidenceSnapshotRow).where(col(EvidenceSnapshotRow.scan_id) == scan_id)
            )
        ).all()
        assert len(ev) == 1  # evidência é imutável: sobrevive ao delete do scan
