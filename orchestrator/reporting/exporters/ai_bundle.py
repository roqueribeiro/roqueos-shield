"""AI Fix Bundle exporter — JSON estruturado pra outra IA consumir e patchar código.

Schema versionado em `docs/ai-fix-bundle-spec.md`. Patcher externo
(Claude Code, Cursor, Copilot) recebe esse JSON e produz patches.

Determinístico: mesmo scan_id → mesmo bundle (modulo timestamps).
`vulnerabilities[].id` é uuid5(deduped_key) — estável entre runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid5

import structlog
from sqlmodel import select

from orchestrator.domain.scrubber import scrub
from orchestrator.persistence.db import session
from orchestrator.persistence.models import FindingRow, ScanRow, TargetRow

log = structlog.get_logger(__name__)

SCHEMA_VERSION = "1.0.0"

# UUID namespace estável pra derivar IDs determinísticos a partir do deduped_key.
_BUNDLE_UUID_NS = UUID("d4a3f8c9-1e2b-4a5c-9b3d-7c8e6f5a2b1c")

# Mapa adapter → categoria pro patcher entender o tipo de fix
_CATEGORY_BY_TOOL: dict[str, str] = {
    "nmap": "infra",
    "zap": "web",
    "nuclei": "web",
    "trivy": "deps",
    "greenbone": "infra",
    "gitleaks": "secret",
    "trufflehog": "secret",
    "github_exposure": "osint",
    "dnstwist": "osint",
    "shodan": "osint",
    "censys": "osint",
    "subdomain_takeover": "osint",
    "checkov": "misconfig",
    "kube_bench": "k8s",
}

_LOCATION_KIND_BY_CATEGORY: dict[str, str] = {
    "web": "http_endpoint",
    "infra": "host_port",
    "deps": "container_layer",
    "secret": "repo_path",
    "osint": "domain",
    "misconfig": "file_path",
    "k8s": "k8s_resource",
}

_DEFAULT_APPROACH_BY_CATEGORY: dict[str, str] = {
    "web": "code_change",
    "infra": "config_change",
    "deps": "dependency_upgrade",
    "secret": "secret_rotation",
    "osint": "manual",
    "misconfig": "config_change",
    "k8s": "config_change",
}

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


async def build_bundle(scan_id: UUID) -> dict[str, Any]:
    """Gera o AI Fix Bundle completo pra um scan_id."""

    async with session() as s:
        scan = await s.get(ScanRow, scan_id)
        if scan is None:
            raise ValueError(f"scan {scan_id} não encontrado")

        target = await s.get(TargetRow, scan.target_id)
        rows = (await s.exec(select(FindingRow).where(FindingRow.scan_id == scan_id))).all()

    log.info("bundle.build_start", scan_id=str(scan_id), findings=len(rows))

    vulnerabilities = [_finding_to_vuln(r) for r in rows]
    # ordenar por patch_priority (1 = urgente)
    vulnerabilities.sort(key=lambda v: v["patch_priority"])

    bundle = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "generator": {
            "tool": "cai",
            "version": "0.3.0",
            "model_used": _detect_model_used(rows),
        },
        "scan": {
            "id": str(scan_id),
            "started_at": scan.started_at.isoformat() if scan.started_at else None,
            "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
            **_coverage(scan),
        },
        "target": _target_section(target, rows),
        "summary": _summary(vulnerabilities),
        "compliance": _compliance_section(rows),
        "vulnerabilities": vulnerabilities,
        "appendix": {
            "raw_scan_artifacts": [
                {"tool": r.source_tool, "path": str(scan.report_path)}
                for r in rows[:1]
                if scan.report_path
            ],
            "scrubbing_applied": [
                "cpf",
                "cnpj",
                "pan_luhn",
                "cvv",
                "email",
                "jwt",
                "aws_keys",
                "auth_header",
                "phone_br",
            ],
            "patcher_instructions": (
                "Process vulnerabilities in patch_priority order. For each, run "
                "code_search_patterns against the repo, propose a patch following "
                "before_after_examples. Use verification.rerun to confirm fix."
            ),
        },
    }

    log.info("bundle.build_done", scan_id=str(scan_id), vulns=len(vulnerabilities))
    return bundle


def _compliance_section(rows: list[FindingRow]) -> dict[str, Any]:
    """Agrega compliance (OWASP/PCI/LGPD/CWE-Top25 + nota de postura A–F)
    reconstruindo as findings a partir do payload persistido. O AI patcher (e o
    GRC do cliente) recebe os frameworks junto do bundle."""
    from orchestrator.domain.schemas import Finding
    from orchestrator.reporting.compliance import build_compliance_report

    findings = []
    for r in rows:
        try:
            findings.append(Finding.model_validate(r.payload))
        except Exception:  # noqa: BLE001, S112
            continue
    rep = build_compliance_report(findings)
    return {
        "risk_grade": rep.risk_grade,
        "risk_index": rep.risk_index,
        "max_cvss": rep.max_cvss,
        "owasp_top10_2021": rep.owasp_coverage,
        "pci_dss_4_0": rep.pci_dss_coverage,
        "lgpd": rep.lgpd_coverage,
        "cwe_top25_2023": list(rep.cwe_top25_unique),
    }


def _detect_model_used(rows: list[FindingRow]) -> str | None:
    for r in rows:
        triage = (r.payload or {}).get("ai_triage")
        if isinstance(triage, dict) and triage.get("model_used"):
            return triage["model_used"]
    return None


def _coverage(scan: ScanRow) -> dict[str, Any]:
    """O que REALMENTE rodou, o que não rodou, e se a cobertura ficou completa.

    `scanners_executed` vinha de `requested_scanners` — ou seja, anunciava como
    executado o que tinha sido apenas PEDIDO. Um scanner sem binário, com serviço
    fora do ar ou sem credencial contribui zero e some do relatório, e quem lê
    conclui que o vetor foi verificado. Era o caso do trivy em produção: sem o
    binário na imagem, um scan de IMAGE não rodava nada e o relatório dizia "trivy".

    A IA de patch precisa desta distinção: "zero achados de SAST" só vale alguma
    coisa se o SAST rodou.
    """
    pedidos = list(scan.requested_scanners or [])
    falhos = sorted({e.split(":", 1)[0].strip() for e in (scan.errors or []) if ":" in e})
    executados = [s for s in pedidos if s not in falhos]
    return {
        "scanners_requested": pedidos,
        "scanners_executed": executados,
        "scanners_failed": falhos,
        "coverage_complete": not falhos,
        "coverage_note": (
            "Todos os scanners pedidos rodaram."
            if not falhos
            else "COBERTURA INCOMPLETA: "
            + ", ".join(falhos)
            + " não rodaram. Zero achados destes vetores NÃO significa alvo limpo."
        ),
    }


def _target_section(
    target: TargetRow | None, rows: list[FindingRow] | None = None
) -> dict[str, Any]:
    rows = rows or []
    if target is None:
        return {
            "primary_value": "unknown",
            "asset_type": "unknown",
            "scope": [],
            "out_of_scope": [],
            "tech_stack_hints": derive_tech_stack(rows),
            "source_code_available_to_patcher": False,
        }
    return {
        "primary_value": target.value,
        "asset_type": target.asset_type,
        "label": target.label,
        "scope": [target.value],
        "out_of_scope": [],
        "contains_pii": target.contains_pii,
        "tech_stack_hints": derive_tech_stack(rows, target),
        # REPO = o patcher tem o código-fonte à mão (o scan veio dele).
        "source_code_available_to_patcher": target.asset_type == "repo",
    }


# Sinais de stack que os scanners já entregam de graça — o bundle mandava tudo
# vazio ("TODO: derivar de evidências"), então a IA de patch não sabia nem a
# linguagem. Derivação determinística, sem I/O e sem LLM.
_LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".rs": "rust",
    ".kt": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
}
_FILE_SIGNALS: dict[str, tuple[str, str]] = {
    "requirements.txt": ("package_managers", "pip"),
    "pyproject.toml": ("package_managers", "pip"),
    "package.json": ("package_managers", "npm"),
    "yarn.lock": ("package_managers", "yarn"),
    "go.mod": ("package_managers", "go modules"),
    "pom.xml": ("package_managers", "maven"),
    "build.gradle": ("package_managers", "gradle"),
    "gemfile": ("package_managers", "bundler"),
    "composer.json": ("package_managers", "composer"),
    "dockerfile": ("runtimes", "docker"),
    "docker-compose.yml": ("runtimes", "docker compose"),
}
_SERVER_HINTS: tuple[str, ...] = (
    "nginx",
    "apache",
    "iis",
    "tomcat",
    "jetty",
    "gunicorn",
    "uvicorn",
    "express",
    "openssh",
    "mysql",
    "postgresql",
    "redis",
    "mongodb",
)


def derive_tech_stack(rows: list[FindingRow], target: TargetRow | None = None) -> dict[str, Any]:
    """Deriva pistas de stack das evidências que os scanners já produziram.

    Fontes: caminho de arquivo (semgrep/gitleaks/checkov/trivy) para linguagem e
    gerenciador de pacote; banner de serviço (nmap) para servidor; alvo REPO/IMAGE
    para repositório e imagem. Determinístico: mesmo scan, mesmo resultado.
    """
    langs: set[str] = set()
    pkgs: set[str] = set()
    runtimes: set[str] = set()
    servers: set[str] = set()
    repos: set[str] = set()
    images: set[str] = set()

    for r in rows:
        payload = r.payload or {}
        value = str(((payload.get("target") or {}).get("value")) or "")
        low = value.lower()
        base = low.rsplit("/", 1)[-1].split(":", 1)[0]
        for ext, lang in _LANG_BY_EXT.items():
            if low.split(":", 1)[0].endswith(ext):
                langs.add(lang)
        if base in _FILE_SIGNALS:
            bucket, name = _FILE_SIGNALS[base]
            (pkgs if bucket == "package_managers" else runtimes).add(name)
        if r.source_tool == "nmap":
            blob = f"{value} {payload.get('description', '')}".lower()
            for hint in _SERVER_HINTS:
                if hint in blob:
                    servers.add(hint)

    if target is not None:
        if target.asset_type == "repo":
            repos.add(target.value)
        elif target.asset_type == "image":
            images.add(target.value)

    found = any([langs, pkgs, runtimes, servers, repos, images])
    return {
        "languages": sorted(langs),
        "frameworks": [],
        "runtimes": sorted(runtimes),
        "servers": sorted(servers),
        "package_managers": sorted(pkgs),
        "source_repos": sorted(repos),
        "container_images": sorted(images),
        # honesto: é derivação de evidência, não introspecção do projeto
        "confidence": "medium" if found else "low",
    }


def _empty_tech_stack() -> dict[str, Any]:
    return {
        "languages": [],
        "frameworks": [],
        "runtimes": [],
        "servers": [],
        "package_managers": [],
        "source_repos": [],
        "container_images": [],
        "confidence": "low",
    }


def _summary(vulns: list[dict[str, Any]]) -> dict[str, Any]:
    counts_sev: dict[str, int] = {s: 0 for s in _SEVERITY_RANK}
    counts_cat: dict[str, int] = {}
    owasp_set: set[str] = set()
    cwe_count: dict[str, int] = {}
    auto_count = 0
    review_count = 0

    for v in vulns:
        counts_sev[v["severity"]] = counts_sev.get(v["severity"], 0) + 1
        counts_cat[v["category"]] = counts_cat.get(v["category"], 0) + 1
        owasp = v["classification"].get("owasp_top10_2021")
        if owasp:
            # extrair só "A03" do "A03:2021-Injection"
            owasp_set.add(owasp.split(":")[0])
        for cwe in v["classification"].get("cwe", []):
            cwe_count[cwe] = cwe_count.get(cwe, 0) + 1
        confidence = v["remediation"]["patch_strategy"]["confidence"]
        if confidence == "high":
            auto_count += 1
        else:
            review_count += 1

    top_cwes = sorted(cwe_count.items(), key=lambda kv: -kv[1])[:5]

    return {
        "counts_by_severity": counts_sev,
        "counts_by_category": counts_cat,
        "owasp_top10_2021": sorted(owasp_set),
        "top_cwes": [c for c, _ in top_cwes],
        "patchable_automatically_count": auto_count,
        "needs_human_review_count": review_count,
    }


def _finding_to_vuln(row: FindingRow) -> dict[str, Any]:
    """Converte um FindingRow do DB num bloco vulnerability do bundle."""
    payload = row.payload or {}
    triage = payload.get("ai_triage") or {}
    cwe = list(payload.get("cwe") or [])

    category = _CATEGORY_BY_TOOL.get(row.source_tool, "infra")
    location_kind = _LOCATION_KIND_BY_CATEGORY.get(category, "host_port")
    approach = _DEFAULT_APPROACH_BY_CATEGORY.get(category, "code_change")
    sev_rank = _SEVERITY_RANK.get(row.severity, 9)

    # uuid estável: namespace + deduped_key
    vuln_id = str(uuid5(_BUNDLE_UUID_NS, row.deduped_key))

    target_obj = payload.get("target") or {}
    target_value = target_obj.get("value") or row.title

    # evidence — passa pelo scrubber antes de servir
    evidence_list = payload.get("evidence") or []
    instances = []
    for ev in evidence_list[:3]:  # máximo 3 evidências por vuln
        instances.append(
            {
                "instance_id": str(uuid5(_BUNDLE_UUID_NS, row.deduped_key + str(ev))),
                "location": _build_location(location_kind, target_value, payload),
                "evidence": _scrub_evidence(ev),
            }
        )

    if not instances:
        # fallback: instância vazia mas com location preenchida
        instances.append(
            {
                "instance_id": str(uuid5(_BUNDLE_UUID_NS, row.deduped_key + "_default")),
                "location": _build_location(location_kind, target_value, payload),
                "evidence": {
                    "scrubbed": True,
                    "description": scrub(payload.get("description", "")),
                },
            }
        )

    return {
        "id": vuln_id,
        "deduped_key": row.deduped_key,
        "title": row.title,
        "category": category,
        "severity": row.severity,
        "severity_original": payload.get("severity", row.severity),
        "confidence": row.confidence,
        "patch_priority": _patch_priority(sev_rank, row.confidence, triage),
        "classification": {
            "owasp_top10_2021": triage.get("owasp_top10"),
            "cwe": cwe,
            "cve": row.vuln_id if row.vuln_id and row.vuln_id.upper().startswith("CVE-") else None,
            "ghsa": row.vuln_id if row.vuln_id and row.vuln_id.upper().startswith("GHSA") else None,
            "cvss_v3": payload.get("cvss_v3"),
            "epss_percentile": None,
            "exploit_available": False,
        },
        "discovered_by": {
            "tool": row.source_tool,
            "rule_id": row.source_rule_id,
            "rule_name": row.title,
            "raw_output_ref": payload.get("raw_output_ref"),
        },
        "instances": instances,
        "remediation": _build_remediation(category, approach, triage, payload),
        "verification": _build_verification(row.source_tool, target_value),
        "ai_triage": {
            "rationale": triage.get("rationale"),
            "is_likely_false_positive": bool(triage.get("is_likely_false_positive", False)),
            "business_impact": triage.get("business_impact"),
            "model_used": triage.get("model_used"),
        }
        if triage
        else None,
    }


def _patch_priority(sev_rank: int, confidence: str, triage: dict[str, Any] | None = None) -> int:
    """1=urgente, 5=cosmético. Combina severity + confidence + triagem da IA.

    A severity aqui já é a AJUSTADA pela IA (o pipeline persiste
    `ai_triage.adjusted_severity` em `FindingRow.severity`; o bundle guarda a do
    scanner em `severity_original`). O que faltava era o outro lado da triagem:
    um finding marcado como provável falso positivo ia pro topo da fila do patcher
    com prioridade cheia. Agora ele vai pro fim — sem sumir do bundle, porque a
    marcação é palpite do LLM, não veredito.
    """
    base = sev_rank + 1  # critical=1, high=2, medium=3, low=4, info=5
    if confidence == "tentative":
        base = min(base + 1, 5)
    if triage and triage.get("is_likely_false_positive"):
        return 5
    return base


def _build_location(kind: str, target_value: str, payload: dict[str, Any]) -> dict[str, Any]:
    base = {"kind": kind}
    if kind == "http_endpoint":
        parsed = urlparse(target_value) if "://" in target_value else None
        base.update(
            {
                "url": target_value,
                "method": "GET",
                "parameter": None,
                "parameter_location": None,
                "request_template": None,
                "host": parsed.hostname if parsed else None,
            }
        )
    elif kind == "host_port":
        host = target_value.split(":")[0]
        port = target_value.split(":")[1] if ":" in target_value else None
        base.update({"host": host, "port": port, "protocol": None})
    elif kind == "repo_path":
        base.update({"path": target_value, "line": None})
    elif kind == "domain":
        base.update({"domain": target_value})
    elif kind == "file_path":
        base.update({"path": target_value, "line": None})
    elif kind == "container_layer":
        base.update({"image": target_value, "package": None, "version": None})
    elif kind == "k8s_resource":
        base.update({"resource_id": target_value})
    return base


def _scrub_evidence(ev: dict[str, Any]) -> dict[str, Any]:
    """Aplica scrubber nos campos de evidência. Trunca payloads enormes."""
    return {
        "scrubbed": True,
        "description": scrub(ev.get("description", ""))[:500],
        "request_sent": scrub(ev.get("request") or "")[:2000] if ev.get("request") else None,
        "response_received_excerpt": (
            scrub(ev.get("response") or "")[:2000] if ev.get("response") else None
        ),
        "payload_used": scrub(ev.get("payload") or "") if ev.get("payload") else None,
        "snippet": scrub(ev.get("snippet") or "") if ev.get("snippet") else None,
    }


def _build_remediation(
    category: str,
    approach: str,
    triage: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    summary = triage.get("suggested_remediation") or payload.get("remediation") or ""
    return {
        "summary": summary,
        "rationale": triage.get("rationale", ""),
        "patch_strategy": {
            "approach": approach,
            "confidence": "high"
            if approach in ("dependency_upgrade", "config_change")
            else "medium",
            "estimated_effort": "small" if approach == "config_change" else "medium",
            "blast_radius": "module" if approach == "code_change" else "service",
        },
        "code_search_patterns": [],  # populado por agent fix-bundle-author quando enrich_with_ai=True
        "before_after_examples": [],
        "dependency_upgrade": None,
        "config_change": None,
        "secret_rotation": (
            {"credential_type": "unknown", "scope": "unknown", "rotation_steps": []}
            if approach == "secret_rotation"
            else None
        ),
        "references": list(payload.get("references") or []),
    }


def _build_verification(tool: str, target_value: str) -> dict[str, Any]:
    return {
        "method": "rerun_scanner",
        "rerun": {
            "scanner": tool,
            "scan_profile": "focused",
            "options": {"target": target_value},
            "expected_outcome": f"no {tool} alert for this rule on this target",
        },
        "http_probe": None,
        "suggested_unit_tests": [],
    }
