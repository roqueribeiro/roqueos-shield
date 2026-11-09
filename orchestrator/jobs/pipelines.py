"""End-to-end pipeline: scan → normalize → dedup → AI triage → persist → report.

CLI roda síncrono. API REST enfileira via arq.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog

from orchestrator.adapters.base import ScannerAdapter, coverage_gap_finding
from orchestrator.adapters.nmap_adapter import NmapAdapter
from orchestrator.adapters.zap_adapter import ZAPAdapter
from orchestrator.ai.analyzer import triage_batch
from orchestrator.ai.observability import emit_phase
from orchestrator.config import settings
from orchestrator.domain.dedup import heuristic_dedup
from orchestrator.domain.schemas import (
    AssetType,
    Finding,
    ScanStatus,
    Target,
)
from orchestrator.reporting.renderer import render_html

log = structlog.get_logger(__name__)


class AdapterUnavailableError(RuntimeError):
    """O scanner não pôde rodar. Zero achados dele não significa alvo limpo."""


# Scanner selection. Before this, run_scan() hardcoded [Nmap, ZAP] and the API's
# `scanners` field was silently dropped — so IMAGE/REPO scans never ran their real
# tools (trivy/gitleaks/checkov) and the field was effectively dead. Now the
# requested scanners (or an asset-type default) build the adapter list.
# See memory roqueshield-image-repo-scanning.
_DEFAULT_SCANNERS: dict[AssetType, list[str]] = {
    AssetType.URL: ["zap"],
    AssetType.DOMAIN: ["zap"],
    AssetType.HOST: ["nmap"],
    AssetType.PORT: ["nmap"],
    AssetType.IMAGE: ["trivy"],
    AssetType.REPO: ["semgrep", "gitleaks", "trufflehog", "trivy", "checkov"],
}


# Que asset types cada scanner realmente aceita (espelha o guard do start_scan de
# cada adapter). Sem isto, um scanner incompatível era instanciado, levantava
# ValueError, o erro era engolido, e o scan fechava com ZERO findings — "não achou
# nada" quando na verdade era "não rodou a ferramenta certa".
_SCANNER_ASSET_SUPPORT: dict[str, set[AssetType]] = {
    "nmap": {AssetType.HOST, AssetType.URL, AssetType.DOMAIN, AssetType.PORT},
    "zap": {AssetType.URL, AssetType.HOST, AssetType.DOMAIN},
    "nuclei": {AssetType.URL, AssetType.HOST, AssetType.DOMAIN},
    "greenbone": {AssetType.HOST, AssetType.DOMAIN},
    "trivy": {AssetType.IMAGE, AssetType.REPO},
    "gitleaks": {AssetType.REPO},
    "trufflehog": {AssetType.REPO},
    "checkov": {AssetType.REPO},
    "semgrep": {AssetType.REPO},
}


# O que cada profile da UI promete. Fonte: os textos que o usuário lê no
# RoqueShield (`pentest.wizard.profileDesc`) — "Aplicação web (OWASP): nmap + ZAP +
# Nuclei". O nuclei era órfão e o front não manda `scanners`, então a promessa era
# falsa: o scan web rodava só ZAP passivo. Aqui o profile vira a lista de verdade.
_PROFILE_SCANNERS: dict[str, dict[AssetType, list[str]]] = {
    "web": {
        AssetType.URL: ["zap", "nuclei"],
        AssetType.DOMAIN: ["zap", "nuclei"],
        AssetType.HOST: ["nmap", "zap", "nuclei"],
    },
    "network": {
        AssetType.HOST: ["nmap"],
        AssetType.PORT: ["nmap"],
        AssetType.DOMAIN: ["nmap"],
        AssetType.URL: ["nmap"],
    },
    # "Todos os scanners aplicáveis (mais demorado)" — e liga o active scan do ZAP.
    "full": {
        AssetType.URL: ["nmap", "zap", "nuclei"],
        AssetType.DOMAIN: ["nmap", "zap", "nuclei"],
        AssetType.HOST: ["nmap", "zap", "nuclei"],
        AssetType.PORT: ["nmap"],
        AssetType.IMAGE: ["trivy"],
        AssetType.REPO: ["semgrep", "gitleaks", "trufflehog", "trivy", "checkov"],
    },
}


# Os profiles que o pipeline sabe executar. `web`, `network` e `full` escolhem a lista
# de scanners (`_PROFILE_SCANNERS`); `active` usa a lista padrão do tipo e liga o
# active scan do ZAP (`apply_profile`, em `api/routers/scans.py`). Antes, qualquer
# string passava: `exposure` e `cloud` eram aceitos por `POST /scans`, oferecidos
# pelo MCP, gravados no scan, e rodavam a lista padrão como se fossem `web`. O
# operador pedia OSINT e recebia um scan web passivo, sem aviso.
PERFIS_DO_SCAN: tuple[str, ...] = ("web", "network", "full", "active", "exposure")

# `exposure` não escolhe adapters do pipeline de scan: ele entrega o alvo ao pipeline
# OSINT (`jobs/exposure.py`), com o domínio do alvo como domínio da empresa e a dork
# `"<domínio>"` no GitHub (código público que cita o domínio). O roqueos-front oferece
# esse profile no POST /scans; antes ele rodava a lista padrão do tipo, um scan web
# passivo com o rótulo "Exposure (OSINT)". Os nomes aqui são os vetores que o
# pipeline OSINT registra em `scanners_ran`/`scanners_skipped`.
PERFIL_EXPOSURE = "exposure"
SCANNERS_EXPOSURE: list[str] = [
    "github_exposure",
    "gitleaks",
    "trufflehog",
    "dnstwist",
    "shodan",
    "subdomain_takeover",
]
_TIPOS_EXPOSURE: frozenset[AssetType] = frozenset({AssetType.DOMAIN, AssetType.URL, AssetType.HOST})

# Perfis que existem em outro lugar e por isso merecem um caminho na mensagem.
_PERFIS_DE_OUTRO_PIPELINE: dict[str, str] = {}

# Chave de `scanners_skipped` quando nenhum scanner do pipeline aceita o alvo.
SEM_SCANNER = "pipeline"


class PerfilRecusado(ValueError):
    """`profile` que o pipeline não executa. Recusar é melhor que rodar outra coisa."""


def validar_perfil(profile: str | None) -> str:
    """Normaliza o profile e recusa o que não existe, dizendo o que existe."""
    p = (profile or "").strip().lower()
    if p in PERFIS_DO_SCAN:
        return p
    aceitos = ", ".join(PERFIS_DO_SCAN)
    if p in _PERFIS_DE_OUTRO_PIPELINE:
        raise PerfilRecusado(
            f"profile {p!r} não é um scan: {_PERFIS_DE_OUTRO_PIPELINE[p]} (aceitos: {aceitos})"
        )
    raise PerfilRecusado(f"profile {p!r} não existe (aceitos: {aceitos})")


def resolve_scanners(
    requested: list[str] | None, asset_type: AssetType, profile: str | None = None
) -> list[str]:
    """A lista EFETIVA de scanners: pedido explícito > profile > default do tipo.

    Sempre filtrada pelo que aceita o asset_type. Vazia quando nenhum scanner do
    pipeline aceita o tipo (`k8s_resource`): quem chama recusa ou registra em
    `scanners_skipped`. Os motivos estão em `resolve_scanners_com_motivo`.
    """
    return resolve_scanners_com_motivo(requested, asset_type, profile)[0]


def resolve_scanners_com_motivo(
    requested: list[str] | None, asset_type: AssetType, profile: str | None = None
) -> tuple[list[str], dict[str, str]]:
    """Como `resolve_scanners`, e também o que ficou de fora e por quê.

    O segundo item vai para `scanners_skipped`: scanner pedido com nome desconhecido
    e (com a chave `SEM_SCANNER`) o caso em que nenhum scanner aceita o alvo. Scanner
    conhecido que não se aplica ao tipo só fica de fora (log), sem virar lacuna.
    O fallback antigo para `["nmap"]` mandava um k8s_resource para o nmap, que
    recusava o tipo: o scan fechava com zero achados e parecia limpo.
    """
    pulados: dict[str, str] = {}
    if (profile or "").strip().lower() == PERFIL_EXPOSURE:
        return _resolve_exposure(requested, asset_type)
    if requested:
        conhecidos: list[str] = []
        for n in requested:
            if n not in _SCANNER_ASSET_SUPPORT:
                pulados[n] = (
                    f"scanner desconhecido (o pipeline de scan constrói: "
                    f"{', '.join(sorted(_SCANNER_ASSET_SUPPORT))})"
                )
            elif asset_type not in _SCANNER_ASSET_SUPPORT[n]:
                # Não se aplica ao tipo: fica de fora, e não é lacuna de cobertura (o
                # alvo é verificado pelos que se aplicam). O roqueos-front manda
                # `["nmap", "zap"]` para qualquer tipo; recusar com 422 quebrava os
                # scans de imagem e de repo da tela do RoqueOS.
                log.info("scanner.nao_se_aplica", scanner=n, asset_type=asset_type.value)
            else:
                conhecidos.append(n)
        if conhecidos:
            return conhecidos, pulados
    by_profile = _PROFILE_SCANNERS.get((profile or "").strip().lower(), {}).get(asset_type)
    if by_profile:
        names = _supported_for(by_profile, asset_type)
        if names:
            return names, pulados
    names = _supported_for(_DEFAULT_SCANNERS.get(asset_type, []), asset_type)
    if not names:
        pulados[SEM_SCANNER] = (
            f"nenhum scanner do pipeline de scan aceita asset_type {asset_type.value}: "
            "este alvo não foi verificado"
        )
    return names, pulados


def _resolve_exposure(
    requested: list[str] | None, asset_type: AssetType
) -> tuple[list[str], dict[str, str]]:
    """O profile `exposure` roda o pipeline OSINT inteiro, ou nada.

    `scanners` explícito não se aplica (o pipeline OSINT decide os vetores pelo que
    está configurado) e é ignorado. O alvo precisa ter um domínio: imagem, repo,
    porta e k8s não têm, e esse caso volta como motivo (o `POST /scans` recusa com 422).
    """
    pulados: dict[str, str] = {}
    if requested:
        # O roqueos-front manda `scanners` junto de qualquer profile. No exposure eles
        # não se aplicam: o pipeline OSINT roda inteiro, e a lista pedida só vai ao log.
        log.info("exposure.scanners_ignorados", scanners=list(requested))
    if asset_type not in _TIPOS_EXPOSURE:
        pulados[SEM_SCANNER] = (
            f"o profile exposure precisa de um domínio (url, domain ou host), "
            f"não de asset_type {asset_type.value}"
        )
        return [], pulados
    return list(SCANNERS_EXPOSURE), pulados


def dominio_do_alvo(target: Target) -> str:
    """O domínio que o pipeline OSINT investiga a partir do alvo do scan."""
    from urllib.parse import urlparse

    valor = target.value.strip()
    if target.asset_type == AssetType.URL or "://" in valor:
        return (urlparse(valor).hostname or "").lower()
    return valor.lower().rstrip(".")


async def _run_exposure_como_scan(target: Target, *, scan_id: UUID, skip_ai: bool) -> ScanResult:
    """O profile `exposure` de um scan: o pipeline OSINT, gravado no MESMO scan."""
    from orchestrator.jobs.exposure import run_exposure_scan

    sid = str(scan_id)
    await _ensure_scan_row(scan_id, target)
    await _update_phase(scan_id, "exposure_running")
    emit_phase(sid, "exposure_running")
    dominio = dominio_do_alvo(target)
    result = await run_exposure_scan(
        company_name=target.label or dominio,
        domains=[dominio] if dominio else [],
        github_orgs=[],
        dorks=[f'"{dominio}"'] if dominio else [],
        skip_ai=skip_ai,
        scan_id=scan_id,
        target=target,
    )
    final = "failed" if (result.scanners_skipped and not result.scanners_ran) else "done"
    await _update_phase(scan_id, final)
    emit_phase(sid, final)
    return result


def _supported_for(names: list[str], asset_type: AssetType) -> list[str]:
    """Filtra os scanners pedidos pelos que aceitam este asset_type."""
    out: list[str] = []
    for n in names:
        supported = _SCANNER_ASSET_SUPPORT.get(n)
        if supported is not None and asset_type not in supported:
            log.info("scanner.skipped_incompatible", scanner=n, asset_type=asset_type.value)
            continue
        out.append(n)
    return out


def _build_adapters(
    names: list[str], skipped: dict[str, str] | None = None
) -> list[ScannerAdapter]:
    """Instancia adapters a partir dos nomes pedidos.

    Nome desconhecido não vira só log: com `skipped`, entra lá com o motivo (é o
    `scanners_skipped` do resultado). Sem isso o scan pedia um scanner, não rodava, e
    a cobertura saía completa.
    """
    from orchestrator.adapters.checkov_adapter import CheckovAdapter
    from orchestrator.adapters.gitleaks_adapter import GitleaksAdapter
    from orchestrator.adapters.greenbone_adapter import GreenboneAdapter
    from orchestrator.adapters.nuclei_adapter import NucleiAdapter
    from orchestrator.adapters.semgrep_adapter import SemgrepAdapter
    from orchestrator.adapters.trivy_adapter import TrivyAdapter
    from orchestrator.adapters.trufflehog_adapter import TrufflehogAdapter

    factories: dict[str, Any] = {
        "nmap": lambda: NmapAdapter(),
        "zap": lambda: ZAPAdapter(base_url=settings.ZAP_BASE_URL, api_key=settings.ZAP_API_KEY),
        "trivy": lambda: TrivyAdapter(server_url=settings.TRIVY_SERVER_URL or None),
        "gitleaks": lambda: GitleaksAdapter(),
        "trufflehog": lambda: TrufflehogAdapter(),
        "checkov": lambda: CheckovAdapter(),
        "semgrep": lambda: SemgrepAdapter(),
        # nuclei e greenbone eram órfãos (não construíveis) — pedir por eles caía em
        # scanner.unknown. Agora instanciáveis quando pedidos; o default por asset
        # não muda (compatibilidade com o front, que hoje não os envia).
        "nuclei": lambda: NucleiAdapter(),
        "greenbone": lambda: GreenboneAdapter(
            username=settings.GREENBONE_USERNAME,
            password=settings.GREENBONE_PASSWORD,
            host=settings.GREENBONE_HOST or None,
            port=settings.GREENBONE_PORT,
        ),
    }
    out: list[ScannerAdapter] = []
    for n in names:
        factory = factories.get(n)
        if factory is None:
            log.warning("scanner.unknown", scanner=n)
            if skipped is not None:
                skipped[n] = "scanner desconhecido: o pipeline de scan não sabe construí-lo"
            continue
        out.append(factory())
    return out


@dataclass
class ScanResult:
    scan_id: UUID
    target: Target
    findings: list[Finding] = field(default_factory=list)
    report_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    # Quem REALMENTE rodou, e quem não rodou (com o motivo). Sem isto, o relatório
    # lista o que foi PEDIDO e o leitor conclui que tudo foi verificado.
    scanners_ran: list[str] = field(default_factory=list)
    scanners_skipped: dict[str, str] = field(default_factory=dict)

    @property
    def coverage_is_complete(self) -> bool:
        """True quando todo scanner pedido de fato rodou."""
        return not self.scanners_skipped


async def _run_adapter(
    adapter: ScannerAdapter,
    target: Target,
    options: dict[str, Any],
    poll_every: float = 5.0,
    # Orçamento do laço de poll, e não um cancelamento: esgotado, vira
    # AdapterUnavailableError (scanners_skipped) e o cleanup do `finally` ainda roda.
    timeout: float = 1800.0,  # noqa: ASYNC109
    scan_id_str: str | None = None,
) -> list[Finding]:
    """Lifecycle completo de um scan: start → poll → fetch → normalize → cleanup.

    REGRA: lista vazia significa "rodou e não achou". Qualquer coisa que impeça a
    verificação — health falso, handle inválido, status FAILED, timeout — levanta
    `AdapterUnavailableError`, e o `run_scan` registra em `scanners_skipped`. Sem
    isso, um clone que falha vira "0 segredos, cobertura completa".

    Garante via `finally` que `adapter.cleanup(handle)` seja chamado, quando
    o adapter expoe o metodo opcional. Previne vazamento de asyncio.Task,
    diretorios temp, e excecoes nao-resgatadas (H7).
    """

    if not await adapter.health():
        # NÃO é "zero findings": é "não verifiquei". A diferença precisa chegar ao
        # resultado, não morrer num log — senão o relatório anuncia um scanner que
        # nunca rodou. Aconteceu em produção: sem o binário do trivy, um scan de
        # IMAGE não rodava NADA e a tela continuava listando "trivy".
        raise AdapterUnavailableError(
            f"{adapter.name} indisponível (health check falhou): binário ausente, "
            "serviço fora do ar, ou credencial faltando. O scan NÃO verificou este "
            "vetor — não confunda com 'nada encontrado'."
        )

    handle = await adapter.start_scan(target, options)
    if not handle or not handle.native_id:
        raise AdapterUnavailableError(
            f"{adapter.name} não devolveu um handle válido: o scan não começou."
        )
    log.info("scan.started", adapter=adapter.name, native_id=handle.native_id)

    try:
        elapsed = 0.0
        while elapsed < timeout:
            status = await adapter.poll(handle)
            if status == ScanStatus.DONE:
                break
            if status in (ScanStatus.FAILED, ScanStatus.CANCELED):
                raise AdapterUnavailableError(
                    f"{adapter.name} terminou com status {status.value}: clone que "
                    "falhou, binário que estourou, serviço que caiu. NÃO verificou "
                    "este vetor."
                )
            await asyncio.sleep(poll_every)
            elapsed += poll_every
        else:
            raise AdapterUnavailableError(
                f"{adapter.name} estourou o timeout de {timeout:.0f}s. Ferramenta "
                "pendurada (rede sem egress é a causa clássica) não é alvo limpo."
            )

        raw = await adapter.fetch_results(handle)
        findings = await adapter.normalize(raw)
        # Lacuna de cobertura não fatal declarada pelo adapter vira achado INFO. Fica
        # AQUI, e não em cada normalize(), porque quinze adapters lembrarem de fazer
        # isso é convenção; um lugar só é mecanismo.
        gaps = list(getattr(raw, "coverage_gaps", None) or [])
        if gaps:
            log.warning("adapter.coverage_gap", adapter=adapter.name, gaps=gaps)
            findings.append(
                coverage_gap_finding(
                    adapter=adapter.name,
                    gaps=gaps,
                    scan_id=UUID(scan_id_str) if scan_id_str else uuid4(),
                    target=target,
                )
            )
        return findings
    finally:
        cleanup = getattr(adapter, "cleanup", None)
        if cleanup is not None:
            try:
                await cleanup(handle)
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "adapter.cleanup_failed",
                    adapter=adapter.name,
                    native_id=handle.native_id,
                    error=str(e),
                )


async def run_scan(
    target: Target,
    *,
    adapters: list[ScannerAdapter] | None = None,
    scanners: list[str] | None = None,
    skip_ai: bool = False,
    options: dict[str, dict[str, Any]] | None = None,
    scan_id: UUID | None = None,
    auth_headers: dict[str, str] | None = None,
    openapi_url: str | None = None,
    profile: str | None = None,
) -> ScanResult:
    """Pipeline completo da Fase 1.

    Args:
        target: alvo da varredura.
        adapters: lista de adapters; None = resolve por `scanners`, profile e
            asset_type (`resolve_scanners_com_motivo`).
        skip_ai: se True, pula AIAnalyzer (útil quando não há API key).
        options: dict por adapter — `{"nmap": {...}, "zap": {...}}`.
        scan_id: id do scan a ATUALIZAR (criado por POST /scans). None = cria novo.
    """
    scan_id = scan_id or uuid4()
    options = dict(options or {})
    if adapters is None and (profile or "").strip().lower() == PERFIL_EXPOSURE:
        _, pulados = _resolve_exposure(scanners, target.asset_type)
        if not pulados:
            return await _run_exposure_como_scan(target, scan_id=scan_id, skip_ai=skip_ai)
    # O que ficou de fora já na resolução (nome desconhecido, tipo incompatível, alvo
    # sem scanner) entra em `scanners_skipped` com o motivo, junto com o que falhar
    # ao rodar. Sem scanner nenhum o scan termina `failed`: nada foi verificado.
    pulados_na_resolucao: dict[str, str] = {}
    if adapters is None:
        names, pulados_na_resolucao = resolve_scanners_com_motivo(
            scanners, target.asset_type, profile
        )
        log.info(
            "scan.scanners_resolved",
            scanners=names,
            profile=profile,
            skipped=list(pulados_na_resolucao),
        )
        adapters = _build_adapters(names, pulados_na_resolucao)
    # Trivy: default internal scanners to vuln+secret+misconfig (CVEs + embedded
    # secrets + Dockerfile/IaC misconfig) unless the caller already set it.
    if any(getattr(a, "name", "") == "trivy" for a in adapters):
        options.setdefault("trivy", {}).setdefault("scanners", "vuln,secret,misconfig")

    result = ScanResult(scan_id=scan_id, target=target)
    for nome, motivo in pulados_na_resolucao.items():
        result.scanners_skipped[nome] = motivo
        result.errors.append(f"{nome}: {motivo}")
    sid = str(scan_id)
    # Cria ScanRow upfront pra que AIRun.scan_id (FK) seja válido durante triage
    await _ensure_scan_row(scan_id, target)
    await _update_phase(scan_id, "queued")
    emit_phase(sid, "queued")

    # roda adapters em sequência (na fase 1, simples). Paralelo vem com arq.
    for adapter in adapters:
        phase = f"{adapter.name}_running"
        await _update_phase(scan_id, phase)
        emit_phase(sid, phase)
        adapter_opts = dict(options.get(adapter.name, {}))
        # Authenticated scanning: feed the auth context to the HTTP scanners
        # ONLY (nmap is a port scanner — headers/openapi are meaningless there).
        # The secret never lands here from the persisted scan row; it arrives
        # as an ephemeral job arg (see run_scan_job).
        if adapter.name in ("zap", "nuclei"):
            if auth_headers:
                adapter_opts["headers"] = auth_headers
            if openapi_url:
                adapter_opts["openapi_url"] = openapi_url
        try:
            findings = await _run_adapter(adapter, target, adapter_opts, scan_id_str=sid)
            for f in findings:
                f.scan_id = scan_id  # sobrescreve placeholder dos adapters
            result.findings.extend(findings)
            result.scanners_ran.append(adapter.name)
        except AdapterUnavailableError as e:
            # Cobertura incompleta: o vetor não foi verificado.
            log.error("adapter.unavailable", adapter=adapter.name, reason=str(e))
            result.scanners_skipped[adapter.name] = str(e)
            result.errors.append(f"{adapter.name}: {e}")
        except Exception as e:  # noqa: BLE001
            log.exception("adapter.crashed", adapter=adapter.name, error=str(e))
            result.scanners_skipped[adapter.name] = f"falhou: {e}"
            result.errors.append(f"{adapter.name}: {e}")

    # Dedupe heurístico (rápido, determinístico)
    await _update_phase(scan_id, "dedup")
    emit_phase(sid, "dedup")
    result.findings = heuristic_dedup(result.findings)

    # AI triage
    if not skip_ai and result.findings:
        await _update_phase(scan_id, "ai_triage")
        emit_phase(sid, "ai_triage")
        try:
            # Triage EVERY finding (skip_severities=set()) — hardened targets
            # often yield only low/info findings, and skipping them meant the AI
            # never ran at all ("connected a key but it's not using AI"). The AI
            # is the whole value prop, so always exercise it.
            await triage_batch(result.findings, scan_id=scan_id, skip_severities=set())
        except Exception as e:  # noqa: BLE001
            log.exception("ai.triage_failed", error=str(e))
            result.errors.append(f"ai_triage: {e}")

    # Relatório ANTES da persistência: o `report_path` precisa existir para ser
    # gravado na linha do scan. Sem isso `GET /reports/{id}` devolvia 404 SEMPRE, e
    # o relatório técnico — o único artefato que renderiza `errors` — ficava num
    # arquivo em disco que rota nenhuma servia.
    await _update_phase(scan_id, "reporting")
    emit_phase(sid, "reporting")
    settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = settings.REPORTS_DIR / f"scan-{scan_id}.html"
    render_html(result, report_path)
    result.report_path = report_path

    # Persistência (Fase 2+) — best-effort: se DB indisponível, segue com HTML
    await _update_phase(scan_id, "persisting")
    emit_phase(sid, "persisting")
    try:
        await _persist_findings(scan_id, target, result.findings, result)
    except Exception as e:  # noqa: BLE001
        log.warning("persist.failed", error=str(e))
        result.errors.append(f"persist: {e}")

    # A fase segue o mesmo critério do state: nada rodou = falhou.
    final_phase = "failed" if (result.scanners_skipped and not result.scanners_ran) else "done"
    await _update_phase(scan_id, final_phase)
    emit_phase(sid, final_phase)

    if result.scanners_skipped:
        log.error(
            "scan.incomplete_coverage",
            scan_id=str(scan_id),
            skipped=list(result.scanners_skipped),
            detail="estes vetores NÃO foram verificados; zero achados deles não é "
            "sinal de alvo limpo",
        )
    log.info(
        "scan.complete",
        scan_id=str(scan_id),
        findings=len(result.findings),
        scanners_ran=result.scanners_ran,
        scanners_skipped=list(result.scanners_skipped),
        coverage_complete=result.coverage_is_complete,
        report=str(report_path),
        errors=result.errors,
    )

    # cleanup HTTP clients
    for adapter in adapters:
        if hasattr(adapter, "aclose"):
            await adapter.aclose()

    return result


async def _ensure_scan_row(scan_id: UUID, target: Target) -> None:
    """Best-effort: cria/garante TargetRow + ScanRow(state=running) upfront.

    Necessário pra que AIRun.scan_id (FK -> scans.id) seja válido durante
    triage. Se DB indisponível, falha silenciosa (telemetria perdida, mas
    scan continua).
    """
    try:
        from sqlmodel import select

        from orchestrator.persistence.db import session
        from orchestrator.persistence.models import ScanRow, ScanState, TargetRow

        async with session() as s:
            existing = (
                await s.exec(select(TargetRow).where(TargetRow.value == target.value))
            ).first()
            if existing is None:
                target_row = TargetRow(
                    asset_type=target.asset_type.value,
                    value=target.value,
                    label=target.label,
                    criticality=target.criticality.value,
                    contains_pii=target.contains_pii,
                )
                s.add(target_row)
                await s.flush()
            else:
                target_row = existing

            # Upsert: POST /scans already created this ScanRow (state=pending) and
            # the UI is watching that id — so UPDATE it to running instead of
            # inserting a duplicate (which would collide on the PK and orphan the
            # UI's scan in `pending` forever). Only create when truly absent.
            scan_row = await s.get(ScanRow, scan_id)
            if scan_row is None:
                scan_row = ScanRow(
                    id=scan_id,
                    target_id=target_row.id,
                    state=ScanState.RUNNING.value,
                    started_at=datetime.now(UTC),
                )
                s.add(scan_row)
            else:
                scan_row.state = ScanState.RUNNING.value
                # O começo do scan nunca era gravado: a tela mostrava "—" de duração
                # em todo scan concluído e um tempo decorrido contado a partir de
                # quando a aba abriu (medido no standalone em 06/11/2026).
                if scan_row.started_at is None:
                    scan_row.started_at = datetime.now(UTC)
                if not scan_row.target_id:
                    scan_row.target_id = target_row.id
                s.add(scan_row)
            await s.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("scan.upfront_persist_failed", scan_id=str(scan_id), error=str(e))


async def _update_phase(scan_id: UUID, phase: str, progress: int | None = None) -> None:
    """Best-effort: atualiza ScanRow.current_phase. Falha silenciosamente."""
    try:
        from orchestrator.persistence.db import session
        from orchestrator.persistence.models import ScanRow

        async with session() as s:
            row = await s.get(ScanRow, scan_id)
            if row is None:
                return
            row.current_phase = phase
            row.phase_progress = progress
            await s.commit()
    except Exception as e:  # noqa: BLE001
        log.debug("phase.update_failed", scan_id=str(scan_id), phase=phase, error=str(e))


async def _persist_findings(
    scan_id: Any,
    target: Target,
    findings: list[Finding],
    result: ScanResult | None = None,
) -> None:
    """Best-effort: grava Findings E A COBERTURA em DB.

    A cobertura é a parte que faltava, e era o elo que anulava todo o resto: o
    pipeline calculava `scanners_skipped` corretamente e esta função gravava só
    `state=done` e as findings. Tudo o que a API, a tela e o Fix Bundle liam vinha
    daqui — então um scan em que NENHUM scanner rodou aparecia verde, com
    `errors: []` e `coverage_complete: true`.

    `state` também deixa de ser sempre DONE: quando nada rodou, o scan não terminou,
    ele falhou. Verde é a cor de "alvo limpo".
    """
    from orchestrator.persistence.db import session
    from orchestrator.persistence.models import FindingRow, ScanRow, ScanState, TargetRow

    async with session() as s:
        # acha-or-cria target
        from sqlmodel import select

        existing = (await s.exec(select(TargetRow).where(TargetRow.value == target.value))).first()
        if existing is None:
            target_row = TargetRow(
                asset_type=target.asset_type.value,
                value=target.value,
                label=target.label,
                criticality=target.criticality.value,
                contains_pii=target.contains_pii,
            )
            s.add(target_row)
            await s.flush()
        else:
            target_row = existing

        # ScanRow já criado em _ensure_scan_row. Atualiza estado E cobertura.
        rodaram = list(result.scanners_ran) if result else []
        pulados = dict(result.scanners_skipped) if result else {}
        erros = list(result.errors) if result else []
        # FAILED quando NADA rodou: o scan não verificou coisa alguma, e "done" com
        # zero achados seria lido como alvo limpo. Cobertura parcial continua "done"
        # (houve verificação real) e a lacuna vai nas colunas de cobertura.
        estado = ScanState.FAILED if (pulados and not rodaram) else ScanState.DONE
        caminho = str(result.report_path) if result and result.report_path else None

        existing_scan = await s.get(ScanRow, scan_id)
        if existing_scan is None:
            existing_scan = ScanRow(id=scan_id, target_id=target_row.id)
            s.add(existing_scan)
        existing_scan.state = estado.value
        existing_scan.target_id = target_row.id
        existing_scan.errors = erros
        existing_scan.scanners_ran = rodaram
        existing_scan.scanners_skipped = pulados
        existing_scan.finished_at = datetime.now(UTC)
        if caminho:
            existing_scan.report_path = caminho
        s.add(existing_scan)
        await s.flush()

        for f in findings:
            s.add(
                FindingRow(
                    scan_id=scan_id,
                    target_id=target_row.id,
                    deduped_key=f.deduped_key,
                    source_tool=f.source_tool,
                    source_rule_id=f.source_rule_id,
                    vuln_id=f.vuln_id,
                    title=f.title,
                    severity=(
                        f.ai_triage.adjusted_severity.value if f.ai_triage else f.severity.value
                    ),
                    confidence=f.confidence.value,
                    payload=f.model_dump(mode="json"),
                )
            )
        await s.commit()
