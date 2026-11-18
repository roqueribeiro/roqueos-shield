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

from sqlalchemy import update
from sqlmodel import col

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


async def _transicionar(
    session: AsyncSession,
    approval_id: UUID,
    *,
    para: CommandApprovalStatus,
    decided_by: str | None,
    reason: str | None,
    no_prazo: bool,
) -> bool:
    """Transição ATÔMICA a partir de `pending`: um único `UPDATE ... WHERE status='pending'`
    (e a condição de prazo). Devolve True só se ESTA chamada mudou a linha.

    Ler `pending` e gravar depois, em dois passos, deixava duas requisições simultâneas
    (aprovar e negar, aprovar e expirar) verem `pending` ao mesmo tempo, e a aprovação
    sobrescrevia a negação. Aqui quem chega segundo muda zero linhas e perde.
    `no_prazo=True` só transiciona se ainda não venceu (aprovar/negar); `False` só se já
    venceu (expirar)."""
    agora = datetime.now(UTC)
    stmt = (
        update(CommandApprovalRow)
        .where(col(CommandApprovalRow.id) == approval_id)
        .where(col(CommandApprovalRow.status) == CommandApprovalStatus.PENDING.value)
        .where(
            col(CommandApprovalRow.expires_at) >= agora
            if no_prazo
            else col(CommandApprovalRow.expires_at) < agora
        )
        .values(status=para.value, decided_by=decided_by, decided_at=agora, reason=reason)
        .execution_options(synchronize_session=False)
    )
    resultado = await session.exec(stmt)
    return int(getattr(resultado, "rowcount", 0) or 0) == 1


async def _reler(session: AsyncSession, approval_id: UUID) -> CommandApprovalRow | None:
    # Depois de um UPDATE direto no banco, o objeto em memória está velho: relê SÓ ele.
    # `session.expire_all()` invalidava todas as linhas da sessão, e em AsyncSession o
    # próximo acesso a atributo de qualquer outra linha (o laço do GET /approvals) vira
    # um lazy refresh implícito, que estoura MissingGreenlet e devolve 500.
    row = await session.get(CommandApprovalRow, approval_id)
    if row is not None:
        await session.refresh(row)
    return row


async def _expirar(session: AsyncSession, approval_id: UUID, proposed_by: str | None) -> bool:
    """Expira atomicamente uma pendência vencida e audita. Expirar é decisão terminal
    (nega); sem ator humano, foi o relógio que fechou, e isso vai para a trilha."""
    mudou = await _transicionar(
        session,
        approval_id,
        para=CommandApprovalStatus.EXPIRED,
        decided_by=None,
        reason="tempo limite estourou com a pendência aberta",
        no_prazo=False,
    )
    if mudou:
        await log_audit_event(
            session,
            action="command.expire",
            actor=None,
            resource_type="command_approval",
            resource_id=approval_id,
            metadata={"proposed_by": proposed_by or ""},
        )
    await session.commit()
    return mudou


async def _marcar_expirada(session: AsyncSession, row: CommandApprovalRow) -> CommandApprovalRow:
    """Expira a pendência vencida (atômico) e devolve a linha relida."""
    await _expirar(session, row.id, row.proposed_by)
    atual = await _reler(session, row.id)
    return atual if atual is not None else row


def _checar_quatro_olhos(
    row: CommandApprovalRow, decided_by: str | None, decided_by_is_service: bool
) -> None:
    """Quatro olhos sem brecha. Comparar só o e-mail, e pular quando faltava um dos lados,
    deixava autoaprovar: o `APP_TOKEN` entra como `service@local`, que nunca é igual ao
    e-mail de quem propôs na tela; e uma pendência sem `proposed_by` passava direto."""
    if not settings.APPROVAL_FOUR_EYES:
        return
    if decided_by_is_service:
        raise QuatroOlhos(
            "com quatro olhos, aprovar exige um usuário nomeado; o token de serviço "
            "(APP_TOKEN) não aprova comando"
        )
    propositor = (row.proposed_by or "").strip().casefold()
    aprovador = (decided_by or "").strip().casefold()
    if not propositor:
        raise QuatroOlhos(
            "pendência sem propositor registrado: com quatro olhos não há como provar que "
            "quem aprova é outra pessoa"
        )
    if not aprovador or aprovador == propositor:
        raise QuatroOlhos("quem propôs o comando não aprova o próprio (quatro olhos)")


async def decidir(
    session: AsyncSession,
    approval_id: UUID,
    *,
    aprovar: bool,
    decided_by: str,
    reason: str | None = None,
    decided_by_is_service: bool = False,
) -> CommandApprovalRow:
    """Aprova ou nega uma pendência, atomicamente. Levanta se já decidida, expirada, ou se
    a aprovação fere os quatro olhos. Negar é sempre permitido: barrar é o lado seguro."""
    row = await session.get(CommandApprovalRow, approval_id)
    if row is None:
        raise AprovacaoError("pendência não encontrada")
    if row.status != CommandApprovalStatus.PENDING.value:
        raise JaDecidida(f"pendência já está em {row.status}")
    if _vencida(row):
        await _expirar(session, approval_id, row.proposed_by)
        raise Expirada("pendência expirada; o tempo limite nega")
    if aprovar:
        _checar_quatro_olhos(row, decided_by, decided_by_is_service)

    mudou = await _transicionar(
        session,
        approval_id,
        para=CommandApprovalStatus.APPROVED if aprovar else CommandApprovalStatus.DENIED,
        decided_by=decided_by,
        reason=reason,
        no_prazo=True,
    )
    if not mudou:
        # Alguém decidiu (ou o prazo venceu) entre a leitura e o UPDATE: perdemos a corrida.
        atual = await _reler(session, approval_id)
        if atual is not None and atual.status == CommandApprovalStatus.PENDING.value:
            await _expirar(session, approval_id, atual.proposed_by)
            raise Expirada("pendência expirada; o tempo limite nega")
        estado = atual.status if atual is not None else "desconhecido"
        raise JaDecidida(f"pendência já está em {estado}")

    await log_audit_event(
        session,
        action="command.approve" if aprovar else "command.deny",
        actor=decided_by,
        resource_type="command_approval",
        resource_id=approval_id,
        metadata={"proposed_by": row.proposed_by or ""},
    )
    await session.commit()
    atual = await _reler(session, approval_id)
    if atual is None:
        raise AprovacaoError("pendência sumiu depois da decisão")
    return atual


async def esta_aprovado(session: AsyncSession, approval_id: UUID) -> bool:
    """True só se a pendência está `approved`. Pendência vencida ainda em `pending` é
    expirada (atômico) e devolve False: o ponto de execução pergunta isto e fecha fechado.
    Uma aprovação só acontece dentro do prazo (`_transicionar(no_prazo=True)`), então um
    comando expirado nunca vira `approved` depois."""
    row = await session.get(CommandApprovalRow, approval_id)
    if row is None:
        return False
    if row.status == CommandApprovalStatus.PENDING.value and _vencida(row):
        await _expirar(session, approval_id, row.proposed_by)
        return False
    return row.status == CommandApprovalStatus.APPROVED.value
