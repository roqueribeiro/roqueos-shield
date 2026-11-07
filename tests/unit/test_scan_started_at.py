"""O começo do scan é gravado uma vez, quando ele passa a rodar.

Antes, `started_at` nunca era escrito: a tela mostrava duração "—" em todo scan e o
tempo decorrido contava de quando a aba abriu.
"""

from __future__ import annotations

import uuid

from orchestrator.domain.schemas import AssetType, Severity, Target


async def test_started_at_gravado_e_mantido() -> None:
    from orchestrator.jobs import pipelines
    from orchestrator.persistence.db import init_db, session
    from orchestrator.persistence.models import ScanRow, ScanState, TargetRow

    await init_db()
    alvo = Target(
        asset_type=AssetType.URL,
        value=f"http://alvo-{uuid.uuid4().hex[:6]}",
        criticality=Severity.MEDIUM,
    )
    async with session() as s:
        t = TargetRow(asset_type="url", value=alvo.value, criticality="medium")
        s.add(t)
        await s.flush()
        sid = uuid.uuid4()
        s.add(ScanRow(id=sid, target_id=t.id, state=ScanState.PENDING.value))
        await s.commit()

    await pipelines._ensure_scan_row(sid, alvo)
    async with session() as s:
        primeiro = (await s.get(ScanRow, sid)).started_at  # type: ignore[union-attr]
    assert primeiro is not None

    await pipelines._ensure_scan_row(sid, alvo)
    async with session() as s:
        row = await s.get(ScanRow, sid)
    assert row is not None and row.state == ScanState.RUNNING.value
    assert row.started_at == primeiro
