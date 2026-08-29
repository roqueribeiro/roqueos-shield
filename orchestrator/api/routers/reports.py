"""Reports router — download HTML técnico/executivo, AI Fix Bundle, export DefectDojo."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlmodel import select

from orchestrator.api.deps import Principal, RequireScansRead, RequireScansRun, SessionDep
from orchestrator.persistence.models import FindingRow, ScanRow, TargetRow

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


async def _load_findings(session, scan_id: UUID):
    """Reconstrói os objetos `Finding` (Pydantic) a partir das linhas do scan."""
    from orchestrator.domain.schemas import Finding

    rows = (await session.exec(select(FindingRow).where(FindingRow.scan_id == scan_id))).all()
    findings = []
    descartadas = 0
    for r in rows:
        try:
            findings.append(Finding.model_validate(r.payload))
        except Exception:  # noqa: BLE001 — linha corrompida não derruba o relatório
            descartadas += 1
    if descartadas:
        # NÃO é detalhe: a UI conta as findings direto do FindingRow e mostra "1
        # critical", enquanto o executivo e o compliance recalculam do payload e,
        # descartando a linha, mostravam "nota A, zero achados". Duas telas do mesmo
        # produto discordando, e a que discorda para baixo é a que vai para auditoria.
        log.error(
            "report.findings_descartadas",
            scan_id=str(scan_id),
            descartadas=descartadas,
            total=len(rows),
            detail="payload que não valida no schema atual — o relatório mostra MENOS "
            "achados do que o scan encontrou",
        )
    return findings


@router.get("/{scan_id}")
async def download_report(
    scan_id: UUID, session: SessionDep, _principal: Principal = RequireScansRead
) -> FileResponse:
    scan = await session.get(ScanRow, scan_id)
    if scan is None or not scan.report_path:
        raise HTTPException(404, "relatório não encontrado")
    path = Path(scan.report_path)
    if not path.exists():
        raise HTTPException(404, f"arquivo {path} não existe no disco")
    return FileResponse(path, media_type="text/html", filename=path.name)


@router.get("/{scan_id}/ai-bundle")
async def download_ai_bundle(
    scan_id: UUID, session: SessionDep, _principal: Principal = RequireScansRead
) -> JSONResponse:
    """AI Fix Bundle — JSON estruturado pra outra IA consumir e patchar código.

    Schema versionado em `docs/ai-fix-bundle-spec.md`. Patcher externo
    (Claude Code, Cursor, Copilot) recebe esse JSON e produz patches.
    """
    from orchestrator.reporting.exporters.ai_bundle import build_bundle

    scan = await session.get(ScanRow, scan_id)
    if scan is None:
        raise HTTPException(404, "scan não encontrado")

    try:
        bundle = await build_bundle(scan_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"falha ao gerar bundle: {e}") from e

    return JSONResponse(content=bundle)


@router.get("/{scan_id}/executive", response_class=HTMLResponse)
async def executive_report(
    scan_id: UUID, session: SessionDep, principal: Principal = RequireScansRead
) -> HTMLResponse:
    """Relatório EXECUTIVO HTML — postura de risco (nota A–F) + mapeamento de
    compliance (OWASP Top 10 2021 → PCI DSS 4.0 + LGPD) + CWE Top 25 + top risks.
    Gerado on-demand a partir dos achados persistidos (sempre fresco)."""
    from dataclasses import dataclass, field

    from orchestrator.domain.schemas import Finding, Target
    from orchestrator.reporting.renderer import render_executive

    scan = await session.get(ScanRow, scan_id)
    if scan is None:
        raise HTTPException(404, "scan não encontrado")

    target_row = await session.get(TargetRow, scan.target_id) if scan.target_id else None
    if target_row is not None:
        target = Target(
            asset_type=target_row.asset_type,
            value=target_row.value,
            label=target_row.label,
            criticality=target_row.criticality,
            contains_pii=target_row.contains_pii,
        )
    else:
        target = Target(asset_type="host", value="(desconhecido)")

    findings: list[Finding] = await _load_findings(session, scan_id)

    @dataclass
    class _Result:
        scan_id: UUID
        target: Target
        findings: list
        report_path: Path | None = None
        errors: list = field(default_factory=list)
        # A cobertura vem da LINHA do scan. Antes estes três eram default vazio
        # hardcoded, então o executivo — o documento que vai para auditoria — não
        # tinha como saber que um scanner não rodou, e saía "nota A, zero achados".
        scanners_ran: list = field(default_factory=list)
        scanners_skipped: dict = field(default_factory=dict)

    result = _Result(
        scan_id=scan_id,
        target=target,
        findings=findings,
        report_path=Path(scan.report_path) if scan.report_path else None,
        errors=list(scan.errors or []),
        scanners_ran=list(scan.scanners_ran or []),
        scanners_skipped=dict(scan.scanners_skipped or {}),
    )

    with tempfile.TemporaryDirectory() as tmp:
        out = render_executive(result, Path(tmp) / "executive.html", actor=principal.email)
        html = out.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/{scan_id}/compliance")
async def compliance_report(
    scan_id: UUID, session: SessionDep, _principal: Principal = RequireScansRead
) -> JSONResponse:
    """Mapeamento de compliance em JSON (consumível por GRC/SIEM/auditoria):
    OWASP Top 10 2021, PCI DSS 4.0, LGPD, CWE Top 25, CVSS e nota de postura."""
    from orchestrator.reporting.compliance import build_compliance_report, report_to_dict

    scan = await session.get(ScanRow, scan_id)
    if scan is None:
        raise HTTPException(404, "scan não encontrado")

    findings = await _load_findings(session, scan_id)
    report = build_compliance_report(findings)
    return JSONResponse(content=report_to_dict(report))


@router.post("/{scan_id}/export/defectdojo", status_code=202)
async def export_defectdojo(
    scan_id: UUID, session: SessionDep, _principal: Principal = RequireScansRun
) -> JSONResponse:
    """Exporta findings desse scan pro DefectDojo via API."""
    from orchestrator.reporting.exporters.defectdojo import export_scan

    scan = await session.get(ScanRow, scan_id)
    if scan is None:
        raise HTTPException(404, "scan não encontrado")

    try:
        result = await export_scan(scan_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"falha ao exportar: {e}") from e

    return JSONResponse(content=result)
