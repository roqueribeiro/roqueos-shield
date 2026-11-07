"""Data que sai do banco sempre com fuso UTC.

Medido em 2026-11-07 no standalone (SQLite): a API devolvia `started_at` sem fuso
("2026-11-07T11:51:15"), o navegador lia como hora local e, em São Paulo, o scan feito
agora aparecia "em 3 horas".
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from orchestrator.persistence.models import ScanRow, TargetRow


async def test_sqlite_devolve_data_com_utc(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'd.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    quando = datetime(2026, 11, 7, 11, 51, 15, tzinfo=UTC)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        alvo = TargetRow(value="http://lab", asset_type="url")
        s.add(alvo)
        await s.flush()
        scan = ScanRow(target_id=alvo.id, profile="web", started_at=quando)
        s.add(scan)
        await s.commit()
        sid = scan.id
    async with AsyncSession(engine) as s:
        lido = await s.get(ScanRow, sid)
        assert lido is not None and lido.started_at is not None
        assert lido.started_at.tzinfo is not None
        assert lido.started_at == quando
        assert lido.started_at.isoformat().endswith("+00:00")
    await engine.dispose()
