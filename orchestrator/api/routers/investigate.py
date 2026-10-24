"""Investigate router — agentic deep-dive em finding individual.

POST /investigate/{finding_id} dispara investigação usando CAI framework / fallback Claude
sob HITL (dry_run=true por padrão).

SEC-05: é o endpoint mais perigoso (onde a Onda 2 pluga o agente ofensivo). Exige a
permissão `scans:run` (não só estar autenticado, como antes) e grava no audit_log
ANTES de executar — o threat-model lista este fluxo como crítico a auditar.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from orchestrator.api.deps import Principal, SessionDep, require_permission
from orchestrator.api.ratelimit import rate_limit
from orchestrator.audit import log_audit_event
from orchestrator.domain.roles import Permission
from orchestrator.persistence.models import FindingRow

router = APIRouter(prefix="/investigate", tags=["investigate"])

_RUN = Depends(require_permission(Permission.SCANS_RUN))


class InvestigationIn(BaseModel):
    instructions: str | None = None
    dry_run: bool = True
    max_steps: int = 10


class InvestigationOut(BaseModel):
    finding_id: UUID
    transcript: list[dict]
    final_assessment: str
    dry_run: bool
    trace_url: str | None = None


@router.post(
    "/{finding_id}",
    response_model=InvestigationOut,
    dependencies=[Depends(rate_limit("investigate"))],
)
async def investigate(
    finding_id: UUID,
    body: InvestigationIn,
    session: SessionDep,
    principal: Principal = _RUN,
) -> InvestigationOut:
    finding = await session.get(FindingRow, finding_id)
    if finding is None:
        raise HTTPException(404, "finding não encontrado")

    # SEC-05: registra a intenção ANTES de executar — o comando perigoso fica no
    # trilho mesmo que a execução falhe. dry_run=false é o modo ofensivo.
    await log_audit_event(
        session,
        action="investigate.run",
        actor=principal.email,
        resource_type="finding",
        resource_id=finding_id,
        metadata={
            "dry_run": body.dry_run,
            "max_steps": body.max_steps,
            "has_instructions": bool(body.instructions),
        },
    )
    await session.commit()

    from orchestrator.ai.agentic.cai_expert import investigate_finding

    try:
        result = await investigate_finding(
            finding,
            extra_instructions=body.instructions,
            dry_run=body.dry_run,
            max_steps=body.max_steps,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"investigação falhou: {e}") from e

    # SEC-05 (2ª metade): o que o agente REALMENTE fez também vai pra trilha —
    # cada comando, se rodou ou foi recusado, e por quê.
    commands = [t["decision"] for t in result.get("transcript", []) if "decision" in t]
    if commands:
        await log_audit_event(
            session,
            action="investigate.commands",
            actor=principal.email,
            resource_type="finding",
            resource_id=finding_id,
            metadata={
                "engine": result.get("engine", "narrative"),
                "dry_run": body.dry_run,
                "tool_calls": result.get("tool_calls", 0),
                "commands_executed": result.get("commands_executed", 0),
                "commands": commands[:20],
            },
        )
        await session.commit()

    return InvestigationOut(
        finding_id=finding_id,
        transcript=result.get("transcript", []),
        final_assessment=result.get("final_assessment", ""),
        dry_run=body.dry_run,
        trace_url=result.get("trace_url"),
    )
