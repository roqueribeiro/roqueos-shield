"""Approvals router: aprovação humana por comando (Frente E, modo `ask`).

`GET /approvals` lista as pendências (expirando as vencidas na leitura); `POST
/approvals/{id}/approve` e `/deny` decidem. Exige `commands:approve` (só ADMIN, por
decisão do engajamento). Quatro olhos: quem propôs não aprova o próprio.

Não há rota que execute o comando aqui: aprovar só muda o estado da pendência. O ponto de
execução (o executor agêntico, Frente M) pergunta `esta_aprovado` antes de agir — e uma
pendência vencida responde não.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import col, select

from orchestrator.api.deps import Principal, RequireCommandsApprove, SessionDep
from orchestrator.approvals import service
from orchestrator.persistence.models import CommandApprovalRow, CommandApprovalStatus

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalOut(BaseModel):
    id: UUID
    reference_type: str
    reference_id: UUID | None
    command: str
    # O texto acima foi redigido? Então quem aprova lê o original em
    # GET /approvals/{id}/command antes de decidir.
    command_redacted: bool = False
    proposed_by: str | None
    status: str
    decided_by: str | None
    decided_at: datetime | None
    reason: str | None
    expires_at: datetime
    created_at: datetime


class DecisionIn(BaseModel):
    # Vai para a pendência e para a resposta: limitado e redigido como o comando.
    reason: str | None = Field(default=None, max_length=2000)


def _to_out(r: CommandApprovalRow) -> ApprovalOut:
    return ApprovalOut(
        id=r.id,
        reference_type=r.reference_type,
        reference_id=r.reference_id,
        command=r.command,
        command_redacted=r.command_redacted,
        proposed_by=r.proposed_by,
        status=r.status,
        decided_by=r.decided_by,
        decided_at=r.decided_at,
        reason=r.reason,
        expires_at=r.expires_at,
        created_at=r.created_at,
    )


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    session: SessionDep,
    status: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _principal: Principal = RequireCommandsApprove,
) -> list[ApprovalOut]:
    """Pendências, mais recentes primeiro. Filtra por `status`. Exige `commands:approve`.

    Uma pendência vencida ainda em `pending` é marcada `expired` na leitura — o tempo
    limite nega mesmo sem ninguém decidir."""
    stmt = select(CommandApprovalRow)
    if status:
        stmt = stmt.where(col(CommandApprovalRow.status) == status)
    rows = (
        await session.exec(
            stmt.order_by(
                col(CommandApprovalRow.created_at).desc(), col(CommandApprovalRow.id).desc()
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    saida: list[ApprovalOut] = []
    for r in rows:
        if r.status == CommandApprovalStatus.PENDING.value and service._vencida(r):
            r = await service._marcar_expirada(session, r)
        if status and r.status != status:
            continue
        saida.append(_to_out(r))
    return saida


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
async def approve(
    approval_id: UUID,
    body: DecisionIn,
    session: SessionDep,
    principal: Principal = RequireCommandsApprove,
) -> ApprovalOut:
    """Aprova a pendência. 403 se ferir quatro olhos; 409 se já decidida ou expirada."""
    try:
        row = await service.decidir(
            session,
            approval_id,
            aprovar=True,
            decided_by=principal.email,
            reason=body.reason,
            decided_by_is_service=principal.is_service,
        )
    except service.QuatroOlhos as e:
        raise HTTPException(403, str(e)) from e
    except service.ComandoIndisponivel as e:
        raise HTTPException(409, str(e)) from e
    except service.Expirada as e:
        raise HTTPException(409, str(e)) from e
    except service.JaDecidida as e:
        raise HTTPException(409, str(e)) from e
    except service.AprovacaoError as e:
        raise HTTPException(404, str(e)) from e
    return _to_out(row)


@router.post("/{approval_id}/deny", response_model=ApprovalOut)
async def deny(
    approval_id: UUID,
    body: DecisionIn,
    session: SessionDep,
    principal: Principal = RequireCommandsApprove,
) -> ApprovalOut:
    """Nega a pendência. 409 se já decidida ou expirada."""
    try:
        row = await service.decidir(
            session, approval_id, aprovar=False, decided_by=principal.email, reason=body.reason
        )
    except service.Expirada as e:
        raise HTTPException(409, str(e)) from e
    except service.JaDecidida as e:
        raise HTTPException(409, str(e)) from e
    except service.AprovacaoError as e:
        raise HTTPException(404, str(e)) from e
    return _to_out(row)


class CommandOut(BaseModel):
    command: str


@router.get("/{approval_id}/command", response_model=CommandOut)
async def read_command(
    approval_id: UUID,
    session: SessionDep,
    principal: Principal = RequireCommandsApprove,
) -> CommandOut:
    """O comando EXATO que vai rodar, sem redação, para quem aprova. Exige
    `commands:approve`; a leitura do original fica na trilha (`command.read`). 409 se o
    comando tem trechos redigidos e o original não foi guardado (sem SECRETS_KEY)."""
    try:
        texto = await service.ler_comando_original(session, approval_id, actor=principal.email)
    except service.ComandoIndisponivel as e:
        raise HTTPException(409, str(e)) from e
    except service.AprovacaoError as e:
        raise HTTPException(404, str(e)) from e
    return CommandOut(command=texto)
