"""arq workers — funções que rodam scans em background.

Wraps run_scan() e run_exposure_scan() em job assíncrono.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from orchestrator.domain.schemas import AssetType, Severity, Target

log = structlog.get_logger(__name__)


async def run_scan_job(
    ctx: dict[str, Any],
    *,
    target_value: str,
    asset_type: str,
    criticality: str = "medium",
    contains_pii: bool = False,
    scanners: list[str] | None = None,
    options: dict[str, dict[str, Any]] | None = None,
    actor: str | None = None,
    scan_id: str | None = None,
    auth_headers: dict[str, str] | None = None,
    openapi_url: str | None = None,
    profile: str | None = None,
    code_upload_id: str | None = None,
) -> dict[str, Any]:
    """Job arq: roda pipeline de scan completo.

    `auth_headers`/`openapi_url` chegam SÓ por aqui (arg efêmero do job no Redis,
    consumido + expira) — nunca da `scans` table, que não guarda o segredo.
    """
    from orchestrator.jobs.pipelines import run_scan
    from orchestrator.persistence.db import session as _db_session
    from orchestrator.runtime_settings import aplicar

    # A tela pode ter trocado o modelo de IA ou o escopo desde o último job: este
    # processo é outro, então lê de novo antes de começar.
    async with _db_session() as s:
        await aplicar(s)

    target = Target(
        asset_type=AssetType(asset_type),
        value=target_value,
        criticality=Severity(criticality),
        contains_pii=contains_pii,
    )

    log.info("scan.started", target=target_value, scanners=scanners, actor=actor)

    # Código enviado: extrai numa pasta temporária, escaneia e apaga tudo, a pasta e o
    # tarball, dê certo ou não. O envio é de uso único.
    tmp: Path | None = None
    code_root: Path | None = None
    code_error: str | None = None
    if code_upload_id:
        code_root, code_error, tmp = _preparar_codigo(code_upload_id)

    try:
        # Pass the requested scan_id so the pipeline UPDATES the scan POST /scans
        # created (the one the UI is watching) instead of minting a new id — which
        # left the UI's scan stuck in `pending` forever.
        result = await run_scan(
            target,
            scanners=scanners or None,
            options=options or {},
            scan_id=UUID(scan_id) if scan_id else None,
            auth_headers=auth_headers or None,
            openapi_url=openapi_url or None,
            profile=profile,
            code_root=code_root,
            code_error=code_error,
        )
    finally:
        if code_upload_id:
            from orchestrator import codigo_enviado

            codigo_enviado.apagar(code_upload_id)
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)

    log.info(
        "scan.finished",
        scan_id=str(result.scan_id),
        findings=len(result.findings),
        errors=result.errors,
        actor=actor,
    )

    return {
        "scan_id": str(result.scan_id),
        "findings": len(result.findings),
        "errors": result.errors,
        "report_path": str(result.report_path) if result.report_path else None,
    }


def _preparar_codigo(upload_id: str) -> tuple[Path | None, str | None, Path | None]:
    """(pasta do repo, erro, pasta temporária). Erro vira `scanners_skipped`, não zero."""
    from orchestrator import codigo_enviado
    from orchestrator.config import settings
    from orchestrator.domain.codigo import CodigoRecusado, extrair, fotografar_em_git

    if codigo_enviado.ler(upload_id) is None:
        return None, "o envio não existe mais no disco (expirou ou já foi usado)", None
    tmp = Path(tempfile.mkdtemp(prefix="cai-code-"))
    raiz = tmp / "repo"
    try:
        extrair(
            codigo_enviado.tarball(upload_id),
            raiz,
            max_arquivos=settings.CODE_UPLOAD_MAX_FILES,
            max_bytes=settings.CODE_UPLOAD_MAX_EXTRACTED_MB * 1024 * 1024,
        )
        fotografar_em_git(raiz)
    except CodigoRecusado as e:
        log.error("codigo.preparo_falhou", upload_id=upload_id, erro=str(e))
        return None, str(e), tmp
    return raiz, None, tmp


async def code_upload_purge_job(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: apaga o código enviado que passou de CODE_UPLOAD_TTL_HOURS sem scan."""
    from orchestrator import codigo_enviado

    apagados = codigo_enviado.expurgar_vencidos()
    if apagados:
        log.info("codigo.expurgo", apagados=len(apagados))
    return {"apagados": len(apagados)}


async def run_exposure_job(
    ctx: dict[str, Any],
    *,
    company_name: str,
    domains: list[str] | None = None,
    github_orgs: list[str] | None = None,
    dorks: list[str] | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Job arq: pipeline OSINT/Exposure."""
    from orchestrator.jobs.exposure import run_exposure_scan

    log.info("exposure.started", company=company_name, domains=domains, github_orgs=github_orgs)

    result = await run_exposure_scan(
        company_name=company_name,
        domains=domains or [],
        github_orgs=github_orgs or [],
        dorks=dorks or [],
    )

    log.info(
        "exposure.finished",
        scan_id=str(result.scan_id),
        findings=len(result.findings),
        errors=result.errors,
    )

    return {
        "scan_id": str(result.scan_id),
        "findings": len(result.findings),
        "errors": result.errors,
        "report_path": str(result.report_path) if result.report_path else None,
    }


async def evidence_retention_job(ctx: dict[str, Any]) -> int:
    """Retenção de evidência agendada (cron diário do worker).

    Antes a retenção só rodava se alguém chamasse `POST /evidence/purge`: quem configurava
    `EVIDENCE_RETENTION_DAYS=90` achava que ela estava em vigor sem estar. Com 0 (o
    padrão) não faz nada. O expurgo em si é o mesmo da rota: apaga o corpo, mantém hash e
    registro, audita `evidence.purge` com o ator `retention-job`.
    """
    from orchestrator.config import settings
    from orchestrator.evidence.service import expurgar_antigas
    from orchestrator.persistence.db import session

    dias = settings.EVIDENCE_RETENTION_DAYS
    if dias <= 0:
        return 0
    async with session() as s:
        apagados = await expurgar_antigas(s, dias, actor="retention-job")
    log.info("evidence.retention_done", dias=dias, apagados=apagados)
    return apagados
