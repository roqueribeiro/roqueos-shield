"""Exposure router: Fase 2.5, OSINT scanning.

Grava `exposure.scan` no audit_log antes de enfileirar, como `scan.create` no
`POST /scans`: era o único disparo de trabalho sem rastro na trilha.
"""

from __future__ import annotations

from arq import create_pool
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from orchestrator.api.deps import Principal, RequireScansRun, SessionDep
from orchestrator.api.ratelimit import rate_limit
from orchestrator.audit import log_audit_event
from orchestrator.jobs.queue import _redis_settings

router = APIRouter(prefix="/exposure", tags=["exposure"])


class ExposureIn(BaseModel):
    company_name: str
    domains: list[str] = Field(default_factory=list)
    github_orgs: list[str] = Field(default_factory=list)
    dorks: list[str] = Field(default_factory=list)


class ExposureOut(BaseModel):
    job_id: str
    queued: bool


@router.post(
    "/scan",
    response_model=ExposureOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("exposure"))],
)
async def scan_exposure(
    body: ExposureIn, session: SessionDep, principal: Principal = RequireScansRun
) -> ExposureOut:
    # Audita ANTES de enfileirar e no mesmo commit: job sem linha na trilha não sai.
    await log_audit_event(
        session,
        action="exposure.scan",
        actor=principal.email,
        resource_type="exposure",
        request_body=body.model_dump(mode="json"),
        metadata={
            "company_name": body.company_name,
            "domains": body.domains,
            "github_orgs": body.github_orgs,
            "dorks": len(body.dorks),
        },
    )
    await session.commit()
    pool = await create_pool(_redis_settings())
    job = await pool.enqueue_job(
        "run_exposure_job",
        company_name=body.company_name,
        domains=body.domains,
        github_orgs=body.github_orgs,
        dorks=body.dorks,
    )
    return ExposureOut(job_id=str(job.job_id) if job else "unknown", queued=job is not None)
