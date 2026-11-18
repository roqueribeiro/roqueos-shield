"""Máquina de aprovação de comando (Frente E).

Transições: `pending` → `approved` | `denied` | `expired`. Três invariantes carregam o
resto, e cada uma tem um teste de mutação:

- **Tempo limite NEGA.** Uma pendência além de `expires_at` nunca pode ser aprovada e
  nunca conta como liberada: `esta_aprovado` a vira `expired` e devolve False. Fecha
  fechado — o default seguro de uma trava é barrar, não deixar passar.
- **Quatro olhos.** Com `APPROVAL_FOUR_EYES`, quem propôs não aprova o próprio comando.
- **Decisão é única e auditada.** Só `pending` pode ser decidida; cada decisão (e a
  criação) vai para o `audit_log`. A trilha de quem decidiu o quê é imutável; a pendência
  em si é mutável de propósito.

Nada de juiz LLM aqui, de propósito: modelo aprovando modelo não é aprovação humana.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from orchestrator.audit.logger import log_audit_event
from orchestrator.config import settings
from orchestrator.domain.scrubber import scrub
from orchestrator.persistence.models import CommandApprovalRow, CommandApprovalStatus

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


class AprovacaoError(RuntimeError):
    """Base das falhas de fluxo de aprovação."""


class JaDecidida(AprovacaoError):
    """A pendência já foi aprovada, negada ou expirada — decisão é única."""


class QuatroOlhos(AprovacaoError):
    """Quem propôs o comando não pode aprovar o próprio (APPROVAL_FOUR_EYES)."""


class Expirada(AprovacaoError):
    """A pendência estourou o tempo limite; expirar nega."""


async def criar_pendencia(
    session: AsyncSession,
    *,
    command: str,
    proposed_by: str | None,
    reference_type: str = "investigation",
    reference_id: UUID | None = None,
) -> CommandApprovalRow:
    """Cria a pendência de um comando que a coleira já liberou. O comando é REDIGIDO
    antes de guardar. `expires_at = agora + APPROVAL_TIMEOUT_SECONDS`."""
    agora = datetime.now(UTC)
    row = CommandApprovalRow(
        reference_type=reference_type,
        reference_id=reference_id,
        command=scrub(command),
        proposed_by=proposed_by,
        status=CommandApprovalStatus.PENDING.value,
        expires_at=agora + timedelta(seconds=settings.APPROVAL_TIMEOUT_SECONDS),
        created_at=agora,
    )
    session.add(row)
    await session.flush()
    await log_audit_event(
        session,
        action="command.request",
        actor=proposed_by,
        resource_type="command_approval",
        resource_id=row.id,
        metadata={"reference_type": reference_type},
    )
    await session.commit()
    return row


def _vencida(row: CommandApprovalRow) -> bool:
    return datetime.now(UTC) > row.expires_at


async def _marcar_expirada(session: AsyncSession, row: CommandApprovalRow) -> CommandApprovalRow:
    row.status = CommandApprovalStatus.EXPIRED.value
    row.decided_at = datetime.now(UTC)
    row.reason = "tempo limite estourou com a pendência aberta"
    session.add(row)
    # Expirar é uma decisão terminal (nega); como criar/aprovar/negar, vai para a trilha.
    # Sem ator humano: foi o relógio que fechou. Senão o audit_log não registra quem (ou
    # o quê) fechou o comando.
    await log_audit_event(
        session,
        action="command.expire",
        actor=None,
        resource_type="command_approval",
        resource_id=row.id,
        metadata={"proposed_by": row.proposed_by or ""},
    )
    await session.commit()
    return row


async def decidir(
    session: AsyncSession,
    approval_id: UUID,
    *,
    aprovar: bool,
    decided_by: str,
    reason: str | None = None,
) -> CommandApprovalRow:
    """Aprova ou nega uma pendência. Levanta se já decidida, expirada, ou se o mesmo ator
    que propôs tenta aprovar com quatro-olhos ligado."""
    row = await session.get(CommandApprovalRow, approval_id)
    if row is None:
        raise AprovacaoError("pendência não encontrada")
    if row.status != CommandApprovalStatus.PENDING.value:
        raise JaDecidida(f"pendência já está em {row.status}")
    if _vencida(row):
        await _marcar_expirada(session, row)
        raise Expirada("pendência expirada; o tempo limite nega")
    if aprovar and settings.APPROVAL_FOUR_EYES and decided_by and decided_by == row.proposed_by:
        raise QuatroOlhos("quem propôs o comando não aprova o próprio (quatro olhos)")

    row.status = (
        CommandApprovalStatus.APPROVED.value if aprovar else CommandApprovalStatus.DENIED.value
    )
    row.decided_by = decided_by
    row.decided_at = datetime.now(UTC)
    row.reason = reason
    session.add(row)
    await log_audit_event(
        session,
        action="command.approve" if aprovar else "command.deny",
        actor=decided_by,
        resource_type="command_approval",
        resource_id=row.id,
        metadata={"proposed_by": row.proposed_by or ""},
    )
    await session.commit()
    return row


async def esta_aprovado(session: AsyncSession, approval_id: UUID) -> bool:
    """True só se a pendência está `approved` e não venceu. Pendência vencida é marcada
    `expired` e devolve False — o ponto de execução pergunta isto e fecha fechado."""
    row = await session.get(CommandApprovalRow, approval_id)
    if row is None:
        return False
    if row.status == CommandApprovalStatus.PENDING.value and _vencida(row):
        await _marcar_expirada(session, row)
        return False
    return row.status == CommandApprovalStatus.APPROVED.value
