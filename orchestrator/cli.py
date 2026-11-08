"""CLI: `cai scan` e `cai exposure` para uso direto sem REST."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import structlog
import typer
from rich.console import Console
from rich.table import Table

from orchestrator.config import settings
from orchestrator.domain.schemas import AssetType, Severity, Target
from orchestrator.jobs.exposure import run_exposure_scan
from orchestrator.jobs.pipelines import ScanResult, run_scan

app = typer.Typer(
    name="cai",
    help="CAI orchestrator — vulnerability analysis platform",
    no_args_is_help=True,
)

console = Console()


def _setup_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            (
                structlog.processors.JSONRenderer()
                if settings.LOG_FORMAT == "json"
                else structlog.dev.ConsoleRenderer()
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )


_TIPOS = "|".join(t.value for t in AssetType)


async def _gates_e_auditoria(
    t: Target, authorization_ref: str | None, profile: str | None, scan_id: UUID
) -> list[str]:
    """Os mesmos gates do `POST /scans`, e o `scan.create` na trilha de auditoria.

    Antes a CLI chamava `run_scan` direto: sem escopo (LAB_ONLY, allowlist), sem
    `authorization_ref` e sem auditoria. Quem tinha shell na imagem escaneava fora do
    escopo e não ficava rastro. Lê o escopo gravado pela tela (`aplicar`), como o
    worker, e falha fechado: sem banco não há trilha, e sem trilha não há scan.
    Devolve a lista efetiva de scanners. Levanta `GateRecusado`.
    """
    from orchestrator.api.routers.scans import gates_do_scan, scanners_do_scan
    from orchestrator.audit import log_audit_event
    from orchestrator.persistence.db import init_db, session
    from orchestrator.runtime_settings import aplicar

    try:
        await init_db()
        async with session() as s:
            await aplicar(s)
    except Exception as e:  # noqa: BLE001  banco fora: sem escopo da tela e sem trilha
        raise _ErroDeAuditoria(str(e)) from e
    gates_do_scan(t.value, t.asset_type.value, authorization_ref)
    nomes = scanners_do_scan(None, t.asset_type, profile)
    try:
        async with session() as s:
            await log_audit_event(
                s,
                action="scan.create",
                actor=_ator_da_cli(),
                resource_type="scan",
                resource_id=scan_id,
                authorization_ref=authorization_ref,
                metadata={
                    "target_value": t.value,
                    "target_asset_type": t.asset_type.value,
                    "profile": profile,
                    "scanners": nomes,
                    "lab_only": settings.LAB_ONLY,
                    "via": "cai scan",
                },
            )
            await s.commit()
    except Exception as e:  # noqa: BLE001
        raise _ErroDeAuditoria(str(e)) from e
    return nomes


class _ErroDeAuditoria(RuntimeError):
    """O banco não respondeu: sem escopo gravado e sem trilha, o scan não roda."""


def _ator_da_cli() -> str:
    import getpass

    try:
        return f"cli:{getpass.getuser()}"
    except Exception:  # noqa: BLE001  sem usuário no ambiente (container sem /etc/passwd)
        return "cli:desconhecido"


@app.command()
def scan(
    target: Annotated[str, typer.Argument(help="URL, host, domínio, imagem ou repositório")],
    asset_type: Annotated[str, typer.Option(help=_TIPOS)] = "url",
    criticality: Annotated[str, typer.Option(help="info|low|medium|high|critical")] = "medium",
    contains_pii: Annotated[
        bool,
        typer.Option(
            help="marca o alvo como tratando dado pessoal; vai como contexto para a "
            "triagem. Não troca o modelo: para IA local, configure LLM_API_BASE",
        ),
    ] = False,
    skip_ai: Annotated[bool, typer.Option(help="pula triagem AI")] = False,
    active_zap: Annotated[bool, typer.Option(help="ZAP active scan (mais agressivo)")] = False,
    ajax: Annotated[
        bool | None,
        typer.Option(
            help="AJAX spider pra SPA (JavaScript). Default: acompanha --active-zap, "
            "porque active scan sem ajax nao acha nada numa SPA.",
        ),
    ] = None,
    authorization_ref: Annotated[
        str | None,
        typer.Option(
            help="referência da autorização (ticket, change); obrigatória com "
            "REQUIRE_AUTH_REF=true. Vai para a trilha de auditoria",
        ),
    ] = None,
) -> None:
    """Roda os scanners do tipo do alvo, triagem AI e gera relatorio HTML.

    Passa pelos mesmos gates do POST /scans (escopo, authorization_ref) e grava
    `scan.create` no audit_log antes de começar.
    """
    from orchestrator.api.routers.scans import GateRecusado

    _setup_logging()

    t = Target(
        asset_type=AssetType(asset_type),
        value=target,
        criticality=Severity(criticality),
        contains_pii=contains_pii,
    )
    scan_id = uuid4()
    # ajax acompanha o active por default: numa SPA (Juice Shop e cia.) o active scan
    # sem o ajax spider nao enxerga rota nenhuma e o relatorio sai vazio.
    ajax_on = active_zap if ajax is None else ajax
    options = {"zap": {"active": active_zap, "ajax": ajax_on}}

    async def _tudo() -> ScanResult:
        # Um loop só: o engine do banco prende a conexão ao loop que a abriu.
        nomes = await _gates_e_auditoria(t, authorization_ref, None, scan_id)
        console.print(f"[bold cyan]CAI[/] starting scan against [bold]{t.value}[/]")
        console.print(
            f"  asset_type={t.asset_type} criticality={t.criticality} pii={t.contains_pii}"
        )
        console.print(f"  scanners={nomes} scan_id={scan_id}")
        console.print()
        return await run_scan(t, scanners=nomes, skip_ai=skip_ai, options=options, scan_id=scan_id)

    try:
        result = asyncio.run(_tudo())
    except GateRecusado as e:
        console.print(f"[red]scan recusado ({e.status}):[/] {e.detalhe}")
        raise typer.Exit(2) from e
    except _ErroDeAuditoria as e:
        console.print(
            f"[red]scan recusado:[/] não consegui gravar a trilha de auditoria ({e}). "
            "Sem auditoria o scan não roda."
        )
        raise typer.Exit(2) from e

    table = Table(title="Findings — resumo")
    table.add_column("Tool")
    table.add_column("Severity")
    table.add_column("Title")
    for f in sorted(result.findings, key=lambda x: x.severity)[:20]:
        sev = f.ai_triage.adjusted_severity if f.ai_triage else f.severity
        table.add_row(f.source_tool, sev, f.title[:80])
    console.print(table)

    if result.errors:
        console.print(f"[yellow]Avisos:[/] {result.errors}")

    if result.report_path:
        console.print(f"\n[green]Relatorio:[/] {result.report_path.resolve()}")


@app.command()
def exposure(
    company_name: Annotated[str, typer.Argument(help="Nome da empresa/banco")],
    domains: Annotated[
        list[str] | None, typer.Option(help="Domínios do banco (repetir flag)")
    ] = None,
    github_orgs: Annotated[
        list[str] | None, typer.Option(help="Orgs GitHub (repetir flag)")
    ] = None,
    dorks: Annotated[list[str] | None, typer.Option(help="Dorks GitHub (repetir flag)")] = None,
    config_file: Annotated[
        Path | None,
        typer.Option(help="YAML de config (sobrescreve flags)"),
    ] = None,
    skip_ai: Annotated[bool, typer.Option(help="pula triagem AI")] = False,
) -> None:
    """Scan OSINT/Exposure externa (Fase 2.5). Read-only, sem autorizacao requerida."""
    _setup_logging()
    # Default None em vez de `[]`: a lista default seria a mesma entre chamadas, e o
    # `dorks.append` abaixo a mutaria (B006). Cópia local, sem tocar no argumento.
    domains = list(domains or [])
    github_orgs = list(github_orgs or [])
    dorks = list(dorks or [])

    if config_file and config_file.exists():
        import yaml

        cfg = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        company = cfg.get("company", {})
        company_name = company.get("name", company_name)
        domains = company.get("domains", domains)
        github_orgs = company.get("github_orgs", github_orgs)
        # gerar dorks a partir do template + internal_strings
        if "dorks_template" in cfg:
            tpl = cfg["dorks_template"]
            internals = company.get("internal_strings", [])
            for t in tpl:
                for d in domains:
                    dorks.append(t.format(domain=d, internal_string="", github_org=""))
                for s in internals:
                    dorks.append(t.format(domain="", internal_string=s, github_org=""))
                for g in github_orgs:
                    dorks.append(t.format(domain="", internal_string="", github_org=g))
            dorks = list({d.strip() for d in dorks if d.strip()})

    console.print(f"[bold cyan]CAI exposure[/] for [bold]{company_name}[/]")
    console.print(f"  domains={domains}")
    console.print(f"  github_orgs={github_orgs}")
    console.print(f"  dorks={len(dorks)}")
    console.print()

    result = asyncio.run(
        run_exposure_scan(
            company_name=company_name,
            domains=domains,
            github_orgs=github_orgs,
            dorks=dorks,
            skip_ai=skip_ai,
        )
    )

    table = Table(title="Exposure — resumo")
    table.add_column("Tool")
    table.add_column("Severity")
    table.add_column("Title")
    for f in sorted(result.findings, key=lambda x: x.severity)[:30]:
        sev = f.ai_triage.adjusted_severity if f.ai_triage else f.severity
        table.add_row(f.source_tool, sev, f.title[:80])
    console.print(table)

    if result.errors:
        console.print(f"[yellow]Avisos:[/] {result.errors}")

    if result.report_path:
        console.print(f"\n[green]Relatorio:[/] {result.report_path.resolve()}")


@app.command()
def serve(
    # Default documentado em docs/REFERENCE.md: o mesmo bind do compose, onde quem limita
    # a exposição é o publish de porta (127.0.0.1). Fora de container: --host 127.0.0.1.
    host: Annotated[str, typer.Option()] = "0.0.0.0",  # noqa: S104
    port: Annotated[int, typer.Option()] = 8080,
) -> None:
    """Sobe a API REST (FastAPI + uvicorn)."""
    import uvicorn

    uvicorn.run("orchestrator.main:app", host=host, port=port, reload=False)


@app.command()
def bundle(
    scan_id: Annotated[str, typer.Argument(help="UUID do scan já executado")],
    out: Annotated[
        Path | None,
        typer.Option(help="Path do JSON output. Default: reports/scan-<id>/ai-bundle.json"),
    ] = None,
) -> None:
    """Gera AI Fix Bundle (JSON) pra outra IA consumir e patchar código."""
    import json

    from orchestrator.reporting.exporters.ai_bundle import build_bundle

    _setup_logging()
    scan_uuid = UUID(scan_id)

    data = asyncio.run(build_bundle(scan_uuid))
    out_path = out or settings.REPORTS_DIR / f"scan-{scan_id}" / "ai-bundle.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    n_vulns = len(data.get("vulnerabilities", []))
    counts = data["summary"]["counts_by_severity"]
    console.print(f"[bold green]AI Fix Bundle[/] gerado: [cyan]{out_path.resolve()}[/]")
    console.print(
        f"  schema={data['schema_version']}  vulns={n_vulns}  "
        f"crit={counts['critical']} high={counts['high']} med={counts['medium']}"
    )
    console.print(
        f"  patcher_auto={data['summary']['patchable_automatically_count']}  "
        f"review={data['summary']['needs_human_review_count']}"
    )
    console.print()
    console.print("[dim]Pra entregar a um patcher (Claude Code/Cursor):[/]")
    console.print(f"  cat {out_path} | <patcher>")


if __name__ == "__main__":
    app()
