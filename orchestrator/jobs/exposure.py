"""Pipeline OSINT/Exposure externa (Fase 2.5).

Chama: GitHubExposureAdapter, GitleaksAdapter (em cima dos repos descobertos),
TrufflehogAdapter, DnstwistAdapter, ShodanAdapter, SubdomainTakeoverAdapter.

Read-only sobre dados públicos.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import structlog

from orchestrator.adapters.dnstwist_adapter import DnstwistAdapter
from orchestrator.adapters.github_exposure_adapter import GitHubExposureAdapter
from orchestrator.adapters.gitleaks_adapter import GitleaksAdapter
from orchestrator.adapters.shodan_adapter import ShodanAdapter
from orchestrator.adapters.subdomain_takeover_adapter import SubdomainTakeoverAdapter
from orchestrator.adapters.trufflehog_adapter import TrufflehogAdapter
from orchestrator.ai.analyzer import triage_batch
from orchestrator.config import settings
from orchestrator.domain.schemas import AssetType, Target
from orchestrator.jobs.pipelines import ScanResult, _run_adapter
from orchestrator.reporting.renderer import render_html

log = structlog.get_logger(__name__)


async def run_exposure_scan(
    *,
    company_name: str,
    domains: list[str],
    github_orgs: list[str],
    dorks: list[str],
    skip_ai: bool = False,
    deep_secrets_in_top_repos: int = 5,
) -> ScanResult:
    """Pipeline OSINT — não toca em ativos do banco, só dados públicos.

    1. GitHubExposure: roda dorks contra org/strings sensíveis → repos suspeitos.
    2. GitleaksAdapter + TrufflehogAdapter nos top-N repos descobertos.
    3. DnstwistAdapter em cada domínio do banco.
    4. ShodanAdapter (opt-in via SHODAN_API_KEY).
    5. SubdomainTakeoverAdapter em cada domínio.

    COBERTURA: cada vetor que não roda entra em `scanners_skipped` com o motivo, e
    cada um que roda entra em `scanners_ran`. Antes, as onze saídas de falha daqui
    escreviam só em `errors` e o resultado saía com `coverage_is_complete = True` —
    ou seja, na configuração de estreia (sem GITHUB_TOKEN, sem SHODAN_API_KEY, sem
    dnstwist e sem subfinder no PATH) o relatório de exposição dizia
    "nenhuma exposição encontrada, cobertura completa" tendo consultado NADA.
    """

    scan_id = uuid4()
    company_target = Target(asset_type=AssetType.DOMAIN, value=company_name)
    result = ScanResult(scan_id=scan_id, target=company_target)

    def pulou(nome: str, motivo: str) -> None:
        """Vetor NÃO verificado. Vai para a cobertura, não só para `errors`."""
        result.scanners_skipped[nome] = motivo
        result.errors.append(f"{nome}: {motivo}")

    def rodou(nome: str) -> None:
        if nome not in result.scanners_ran:
            result.scanners_ran.append(nome)

    # 1. GitHub dorks
    gh = GitHubExposureAdapter()
    if await gh.health() and dorks:
        try:
            github_findings = await _run_adapter(
                gh, company_target, options={"dorks": dorks, "max_results_per_dork": 30}
            )
            for f in github_findings:
                f.scan_id = scan_id
            result.findings.extend(github_findings)
            rodou("github_exposure")

            # 2. Top-N repos descobertos → gitleaks + trufflehog
            top_repos = list({f.target.value for f in github_findings})[:deep_secrets_in_top_repos]
            for repo_url in top_repos:
                repo_target = Target(asset_type=AssetType.REPO, value=repo_url)
                for adapter in (GitleaksAdapter(), TrufflehogAdapter()):
                    # O `else` faltava aqui: sem o binário, a varredura profunda de
                    # segredo nos repos descobertos simplesmente não acontecia, e o
                    # relatório dizia "5 repos expostos, nenhum segredo neles".
                    if not await adapter.health():
                        pulou(
                            adapter.name,
                            "binário ausente — os repos descobertos NÃO foram varridos "
                            "atrás de segredo",
                        )
                        continue
                    try:
                        secrets_findings = await _run_adapter(adapter, repo_target, options={})
                        for f in secrets_findings:
                            f.scan_id = scan_id
                        result.findings.extend(secrets_findings)
                        rodou(adapter.name)
                    except Exception as e:  # noqa: BLE001
                        log.exception("exposure.secret_adapter_failed", error=str(e))
                        pulou(adapter.name, f"falhou em {repo_url}: {e}")
        except Exception as e:  # noqa: BLE001
            log.exception("exposure.github_failed", error=str(e))
            pulou("github_exposure", str(e))
    elif dorks:
        pulou("github_exposure", "GITHUB_TOKEN ausente — as dorks não foram consultadas")
    else:
        pulou("github_exposure", "nenhuma dork configurada — nada foi buscado no GitHub")

    # 3. dnstwist por domínio
    dt = DnstwistAdapter()
    if await dt.health():
        for d in domains:
            try:
                dn_target = Target(asset_type=AssetType.DOMAIN, value=d)
                dn_findings = await _run_adapter(dt, dn_target, options={})
                for f in dn_findings:
                    f.scan_id = scan_id
                result.findings.extend(dn_findings)
                rodou("dnstwist")
            except Exception as e:  # noqa: BLE001
                pulou("dnstwist", f"falhou em {d}: {e}")
    else:
        pulou("dnstwist", "binário não disponível — typosquatting não foi verificado")

    # 4. Shodan (opt-in)
    sh = ShodanAdapter()
    # health() UMA vez: chamado duas, um blip entre as duas chamadas fazia o vetor
    # sumir sem registro nenhum (True no primeiro, False no segundo).
    if not await sh.health():
        pulou("shodan", "indisponível (chave ausente ou API fora do ar)")
    else:
        try:
            sh_findings = await _run_adapter(
                sh,
                company_target,
                options={"query": f'org:"{company_name}"', "limit": 100},
            )
            for f in sh_findings:
                f.scan_id = scan_id
            result.findings.extend(sh_findings)
            rodou("shodan")
        except Exception as e:  # noqa: BLE001
            pulou("shodan", str(e))

    # 5. Subdomain takeover por domínio (paralelo)
    st = SubdomainTakeoverAdapter()
    st_ok = await st.health()  # idem shodan: uma chamada só
    if not st_ok:
        pulou("subdomain_takeover", "indisponível (subfinder/httpx/nuclei ausentes)")
    elif not domains:
        pulou("subdomain_takeover", "nenhum domínio informado — nada foi enumerado")
    if st_ok and domains:
        coros = []
        for d in domains:
            dn_target = Target(asset_type=AssetType.DOMAIN, value=d)
            coros.append(_run_adapter(st, dn_target, options={}))
        try:
            results_list = await asyncio.gather(*coros, return_exceptions=True)
            for r in results_list:
                if isinstance(r, Exception):
                    pulou("subdomain_takeover", str(r))
                    continue
                for f in r:
                    f.scan_id = scan_id
                result.findings.extend(r)
                rodou("subdomain_takeover")
        except Exception as e:  # noqa: BLE001
            pulou("subdomain_takeover", str(e))

    # AI triage
    if not skip_ai and result.findings:
        try:
            await triage_batch(result.findings)
        except Exception as e:  # noqa: BLE001
            log.exception("exposure.triage_failed", error=str(e))
            result.errors.append(f"ai_triage: {e}")

    # Relatório
    settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = settings.REPORTS_DIR / f"exposure-{scan_id}.html"
    render_html(result, report_path)
    result.report_path = report_path

    log.info(
        "exposure.complete",
        scan_id=str(scan_id),
        findings=len(result.findings),
        errors=result.errors,
    )

    # cleanup
    if hasattr(gh, "_client") and gh._client:  # noqa: SLF001
        pass  # PyGithub não tem aclose

    return result
