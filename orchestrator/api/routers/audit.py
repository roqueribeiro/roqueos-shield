"""Audit router: leitura da trilha de auditoria (`audit_log`), só leitura.

O papel `auditor` existia em `domain/roles.py` com `audit:read`, e o gate
`RequireAuditRead` existia em `deps.py`, mas rota nenhuma lia a trilha: pela API um
auditor via o mesmo que um viewer. Esta rota é a leitura que faltava.

Não há escrita aqui, de propósito: o `audit_log` é append-only (trigger no Postgres,
`audit/logger.py` no código) e só ganha linha pela ação auditada.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import col, select

from orchestrator.api.deps import Principal, RequireAuditRead, SessionDep
from orchestrator.persistence.models import AuditLogRow

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditOut(BaseModel):
    id: UUID
    created_at: datetime
    actor: str | None
    action: str
    resource_type: str | None
    resource_id: UUID | None
    authorization_ref: str | None
    request_hash: str | None
    metadata: dict[str, Any]


class AuditPage(BaseModel):
    items: list[AuditOut]
    total: int
    offset: int
    limit: int
    has_more: bool


@router.get("", response_model=AuditPage)
async def list_audit(
    session: SessionDep,
    action: str | None = Query(default=None, description="ex.: scan.create"),
    actor: str | None = None,
    resource_id: UUID | None = None,
    authorization_ref: str | None = None,
    since: datetime | None = Query(default=None, description="ISO-8601; só depois disto"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _principal: Principal = RequireAuditRead,
) -> AuditPage:
    """A trilha, mais recente primeiro. Exige `audit:read` (papéis `auditor` e `admin`)."""
    stmt = select(AuditLogRow)
    if action:
        stmt = stmt.where(AuditLogRow.action == action)
    if actor:
        stmt = stmt.where(AuditLogRow.actor == actor)
    if resource_id:
        stmt = stmt.where(AuditLogRow.resource_id == resource_id)
    if authorization_ref:
        stmt = stmt.where(AuditLogRow.authorization_ref == authorization_ref)
    if since:
        stmt = stmt.where(col(AuditLogRow.created_at) > since)

    total = (await session.exec(select(func.count()).select_from(stmt.subquery()))).one()
    # `id` desempata linhas do mesmo instante: sem ele a paginação repete ou pula linha.
    page = (
        stmt.order_by(col(AuditLogRow.created_at).desc(), col(AuditLogRow.id).desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.exec(page)).all()
    items = [
        AuditOut(
            id=r.id,
            created_at=r.created_at,
            actor=r.actor,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            authorization_ref=r.authorization_ref,
            request_hash=r.request_hash,
            metadata=dict(r.metadata_json or {}),
        )
        for r in rows
    ]
    return AuditPage(
        items=items,
        total=int(total),
        offset=offset,
        limit=limit,
        has_more=offset + len(items) < int(total),
    )
