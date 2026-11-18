"""Assets router: leitura do inventário de ativos (Frente A), só leitura.

O inventário é escrito pelo pipeline (`_persist_findings` → `domain.assets.registrar_ativos`);
aqui só se lê. `GET /inventory` lista o que o engagement conhece entre scans; `GET /inventory/{id}`
abre um ativo com as observações (um scan cada, com a cobertura daquele scan) e os findings
ligados a ele.

O veredito cross-scan "sumiu" vs "não verificado" (`domain.assets.classificar_presenca`) vive
na timeline de um alvo e é servido pelo diff da Frente B; aqui a observação carrega a cobertura
do scan para quem for montar esse veredito não precisar adivinhar.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import col, select

from orchestrator.api.deps import Principal, RequireScansRead, SessionDep
from orchestrator.persistence.models import (
    AssetObservationRow,
    AssetRow,
    FindingRow,
    ScanRow,
)

# Prefixo `/inventory`, NÃO `/assets`: a tela standalone é montada em `/` e o build do
# Vite serve o JS/CSS em `/assets/*`. Uma rota de API em `/assets/{id}` captura o pedido
# do bundle antes do StaticFiles (401 JSON no lugar do JavaScript) e a tela não carrega.
# O teste `test_rotas_nao_colidem_com_estaticos_da_tela` trava isso.
router = APIRouter(prefix="/inventory", tags=["inventory"])


class AssetOut(BaseModel):
    id: UUID
    asset_key: str
    asset_type: str
    value: str
    label: str | None
    first_seen: datetime
    last_seen: datetime
    last_scan_id: UUID | None
    technologies: list[str]


class AssetPage(BaseModel):
    items: list[AssetOut]
    total: int
    offset: int
    limit: int
    has_more: bool


class ObservationOut(BaseModel):
    scan_id: UUID
    observed_at: datetime
    source_tool: str | None
    # Cobertura do scan que viu o ativo: sem isto, ausência num scan posterior não dá
    # para classificar entre "sumiu" e "não verificado".
    coverage_complete: bool


class LinkedFindingOut(BaseModel):
    id: UUID
    scan_id: UUID
    deduped_key: str
    title: str
    severity: str


class AssetDetailOut(AssetOut):
    observations: list[ObservationOut]
    findings: list[LinkedFindingOut]


def _to_out(r: AssetRow) -> AssetOut:
    return AssetOut(
        id=r.id,
        asset_key=r.asset_key,
        asset_type=r.asset_type,
        value=r.value,
        label=r.label,
        first_seen=r.first_seen,
        last_seen=r.last_seen,
        last_scan_id=r.last_scan_id,
        technologies=list(r.technologies or []),
    )


@router.get("", response_model=AssetPage)
async def list_assets(
    session: SessionDep,
    asset_type: str | None = Query(default=None, description="host|url|port|image|repo|domain|k8s"),
    q: str | None = Query(default=None, description="substring do valor do ativo"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _principal: Principal = RequireScansRead,
) -> AssetPage:
    """Inventário, visto por último primeiro. Exige `scans:read`."""
    stmt = select(AssetRow)
    if asset_type:
        stmt = stmt.where(AssetRow.asset_type == asset_type)
    if q:
        stmt = stmt.where(col(AssetRow.value).contains(q))

    total = (await session.exec(select(func.count()).select_from(stmt.subquery()))).one()
    page = (
        stmt.order_by(col(AssetRow.last_seen).desc(), col(AssetRow.id).desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.exec(page)).all()
    items = [_to_out(r) for r in rows]
    return AssetPage(
        items=items,
        total=int(total),
        offset=offset,
        limit=limit,
        has_more=offset + len(items) < int(total),
    )


@router.get("/{asset_id}", response_model=AssetDetailOut)
async def get_asset(
    asset_id: UUID,
    session: SessionDep,
    _principal: Principal = RequireScansRead,
) -> AssetDetailOut:
    """Um ativo, com observações (uma por scan, com a cobertura do scan) e findings ligados."""
    row = await session.get(AssetRow, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="ativo não encontrado")

    obs_rows = (
        await session.exec(
            select(AssetObservationRow)
            .where(AssetObservationRow.asset_id == asset_id)
            .order_by(col(AssetObservationRow.observed_at).desc())
        )
    ).all()
    observations: list[ObservationOut] = []
    for o in obs_rows:
        scan = await session.get(ScanRow, o.scan_id)
        # Cobertura completa quando o scan não pulou scanner nenhum.
        coverage_complete = bool(scan is not None and not (scan.scanners_skipped or {}))
        observations.append(
            ObservationOut(
                scan_id=o.scan_id,
                observed_at=o.observed_at,
                source_tool=o.source_tool,
                coverage_complete=coverage_complete,
            )
        )

    finding_rows = (
        await session.exec(
            select(FindingRow)
            .where(FindingRow.asset_id == asset_id)
            .order_by(col(FindingRow.discovered_at).desc())
        )
    ).all()
    findings = [
        LinkedFindingOut(
            id=f.id,
            scan_id=f.scan_id,
            deduped_key=f.deduped_key,
            title=f.title,
            severity=f.severity,
        )
        for f in finding_rows
    ]

    base = _to_out(row)
    return AssetDetailOut(**base.model_dump(), observations=observations, findings=findings)
