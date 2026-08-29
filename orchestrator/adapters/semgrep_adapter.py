"""Semgrep adapter — SAST de código-fonte (o que faltava para "qualidade de código").

Diferente dos scanners de secret (gitleaks/trufflehog), IaC (checkov) e CVE de deps
(trivy), o Semgrep lê o CÓDIGO atrás de bug/vuln: injection, SSRF, path traversal,
crypto fraca, desserialização, uso perigoso de API. Roda sobre um checkout local
(clona a URL do repo, ou usa um diretório já presente).

Soberania: `--metrics off` — nada é enviado pro registry da Semgrep. `--config` é
configurável (default `auto`, que puxa o ruleset público; num ambiente sem egress,
aponte para um pack local via options `{"config": "/rules"}`).
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Evidence,
    Finding,
    RawResults,
    ScanHandle,
    ScanStatus,
    Severity,
    Target,
)

log = structlog.get_logger(__name__)

_SEVERITY_MAP: dict[str, Severity] = {
    "ERROR": Severity.HIGH,
    "WARNING": Severity.MEDIUM,
    "INFO": Severity.LOW,
}
_CONFIDENCE_MAP: dict[str, Confidence] = {
    "HIGH": Confidence.CERTAIN,
    "MEDIUM": Confidence.FIRM,
    "LOW": Confidence.TENTATIVE,
}
_CWE_RE = re.compile(r"CWE-\d+")


class SemgrepAdapter:
    """Roda semgrep sobre um repo (clone efêmero) ou diretório local; JSON → Finding."""

    name = "semgrep"

    def __init__(self, semgrep_bin: str | None = None, git_bin: str | None = None) -> None:
        self.semgrep_bin = semgrep_bin or shutil.which("semgrep") or "semgrep"
        self.git_bin = git_bin or shutil.which("git") or "git"
        self._tasks: dict[str, asyncio.Task[tuple[int, Path]]] = {}
        self._workdirs: dict[str, Path] = {}

    async def health(self) -> bool:
        try:
            p = await asyncio.create_subprocess_exec(
                self.semgrep_bin,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await p.communicate()
            return p.returncode == 0
        except (FileNotFoundError, PermissionError):
            return False

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        if target.asset_type != AssetType.REPO:
            raise ValueError(f"semgrep só suporta REPO, recebi {target.asset_type}")

        workdir = Path(tempfile.mkdtemp(prefix="cai-semgrep-"))
        report_path = workdir / "report.json"
        config = str(options.get("config", "auto"))
        depth = str(options.get("clone_depth", 1))

        # Diretório local já presente (path) vs. URL de repo a clonar.
        local_dir = Path(target.value)
        use_local = local_dir.is_dir()
        clone_dir = local_dir if use_local else (workdir / "repo")

        async def _run() -> tuple[int, Path]:
            if not use_local:
                clone = await asyncio.create_subprocess_exec(
                    self.git_bin,
                    "clone",
                    "--quiet",
                    "--depth",
                    depth,
                    target.value,
                    str(clone_dir),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await clone.communicate()
                if clone.returncode != 0:
                    log.error("semgrep.clone_failed", err=stderr.decode(errors="replace")[:500])
                    return clone.returncode or 1, report_path

            scan = await asyncio.create_subprocess_exec(
                self.semgrep_bin,
                "scan",
                "--config",
                config,
                "--json",
                "--output",
                str(report_path),
                "--quiet",
                "--metrics",
                "off",
                "--disable-version-check",
                # `--time` põe em `time.rules` quantas regras REALMENTE rodaram. É o
                # único sinal que separa "código limpo" de "nenhuma regra carregou"
                # — ver `_rules_ran` abaixo.
                "--time",
                str(clone_dir),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await scan.communicate()
            # semgrep sai 0 mesmo com findings (eles vão pro JSON). >1 é erro real.
            rc = scan.returncode or 0
            if rc > 1:
                log.error("semgrep.scan_failed", rc=rc, err=stderr.decode(errors="replace")[:500])
                return rc, report_path
            return 0, report_path

        native_id = str(uuid4())
        self._workdirs[native_id] = workdir
        self._tasks[native_id] = asyncio.create_task(_run())
        return ScanHandle(
            adapter=self.name,
            native_id=native_id,
            metadata={"repo": target.value, "report": str(report_path), "config": config},
        )

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        task = self._tasks.get(handle.native_id)
        if task is None:
            return ScanStatus.FAILED
        if not task.done():
            return ScanStatus.RUNNING
        rc, _ = task.result()
        return ScanStatus.DONE if rc == 0 else ScanStatus.FAILED

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        _, report_path = self._tasks[handle.native_id].result()
        payload: dict[str, Any] = {}
        if report_path.exists():
            try:
                payload = json.loads(report_path.read_text(encoding="utf-8")) or {}
            except json.JSONDecodeError:
                payload = {}

        # Zero achados só vale como "limpo" se ALGUMA regra rodou. Um `--config`
        # que não resolve (registry sem egress no cliente, pack privado sem
        # credencial, caminho errado) faz o semgrep sair com código 0, zero regras e
        # zero resultados — indistinguível de código são. Reproduzido: config com
        # `rules: []` dá exit 0 / 0 regras / 0 achados. Num banco, egress restrito é
        # o caso normal, então este silêncio seria o comportamento padrão.
        if not _rules_ran(payload):
            raise ScanIntegrityError(
                "semgrep terminou sem carregar NENHUMA regra: o resultado seria um "
                "'limpo' falso. Verifique o --config (registry alcançável? pack "
                "existe? caminho local correto?)."
            )
        return RawResults(adapter=self.name, payload=payload)

    async def normalize(self, raw: RawResults) -> list[Finding]:
        findings: list[Finding] = []
        placeholder = uuid4()
        results = (raw.payload or {}).get("results", []) if isinstance(raw.payload, dict) else []

        for item in results:
            extra = item.get("extra", {}) or {}
            meta = extra.get("metadata", {}) or {}
            check_id = item.get("check_id", "semgrep-rule")
            path = item.get("path", "?")
            line = (item.get("start", {}) or {}).get("line", "?")

            findings.append(
                Finding(
                    scan_id=placeholder,
                    target=Target(asset_type=AssetType.REPO, value=f"{path}:{line}"),
                    source_tool=self.name,
                    source_rule_id=check_id,
                    cwe=_extract_cwes(meta.get("cwe")),
                    title=_short_title(check_id, extra.get("message", "")),
                    description=(
                        f"{extra.get('message', '').strip()}\n"
                        f"Arquivo {path}, linha {line}."
                        + (f" OWASP: {_join(meta.get('owasp'))}." if meta.get("owasp") else "")
                    ).strip(),
                    severity=_SEVERITY_MAP.get(
                        str(extra.get("severity", "INFO")).upper(), Severity.LOW
                    ),
                    confidence=_CONFIDENCE_MAP.get(
                        str(meta.get("confidence", "")).upper(), Confidence.FIRM
                    ),
                    evidence=[
                        Evidence(
                            description=f"Match da regra {check_id} em {path}:{line}",
                            snippet=(extra.get("lines") or "")[:400],
                        )
                    ],
                )
            )
        log.info("semgrep.normalize_done", findings=len(findings))
        return findings

    async def cleanup(self, handle: ScanHandle) -> None:
        from orchestrator.adapters._cleanup import cleanup_subprocess_handle

        await cleanup_subprocess_handle(
            native_id=handle.native_id,
            tasks=self._tasks,  # type: ignore[arg-type]
            output_paths=self._workdirs,
            adapter_name=self.name,
        )


class ScanIntegrityError(RuntimeError):
    """O scan terminou, mas o resultado não é confiável (ex.: nenhuma regra rodou)."""


def _rules_ran(payload: dict[str, Any]) -> int:
    """Quantas regras o semgrep realmente executou (`--time` popula `time.rules`)."""
    if not isinstance(payload, dict):
        return 0
    regras = (payload.get("time") or {}).get("rules")
    return len(regras) if isinstance(regras, list) else 0


def _extract_cwes(raw: Any) -> list[str]:
    """Extrai só os identificadores `CWE-NNN` do metadata (que vem como str ou lista)."""
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for it in items:
        m = _CWE_RE.search(str(it))
        if m and m.group(0) not in out:
            out.append(m.group(0))
    return out


def _short_title(check_id: str, message: str) -> str:
    """Título curto: última parte do check_id + 1ª frase da mensagem."""
    rule = check_id.rsplit(".", 1)[-1].replace("-", " ")
    first = message.strip().split(". ")[0][:120]
    return f"{rule}: {first}" if first else rule or check_id


def _join(v: Any) -> str:
    return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
