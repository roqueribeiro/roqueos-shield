"""Checkov adapter — IaC misconfig scan (Terraform, CloudFormation, K8s manifests, ARM).

O alvo é REPO. `target.value` pode ser um diretório já presente ou uma URL de repo
— e a URL precisa ser CLONADA antes: `checkov -d https://github.com/org/repo` não
clona nada. O checkov apenas loga "Directory does not exist; skipping it", sai com
código 0 e escreve saída VAZIA. Medido nesta máquina (checkov 3.3.15):

    $ checkov -d /tmp/nao_existe -o json --quiet --soft-fail; echo $?
    0
    $ wc -c saida.json
    0

Ou seja: o pior silêncio possível — "nenhum problema de IaC" para um alvo que nunca
foi lido. Por isso este adapter clona (como gitleaks/semgrep), confere o returncode
no `poll`, e trata saída ausente/ilegível como `ScanIntegrityError` em vez de `{}`.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from orchestrator.adapters.base import ScanIntegrityError
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


_CHECKOV_SEVERITY: dict[str, Severity] = {
    "INFO": Severity.INFO,
    "LOW": Severity.LOW,
    "MEDIUM": Severity.MEDIUM,
    "HIGH": Severity.HIGH,
    "CRITICAL": Severity.CRITICAL,
}


def _runs(payload: Any) -> list[dict[str, Any]]:
    """Normaliza a saída do checkov: dict (um framework) ou list (vários)."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _summaries(payload: Any) -> list[dict[str, Any]]:
    """Os blocos `summary` de cada run.

    Quando o checkov não encontra NENHUM arquivo IaC, ele devolve o summary no topo
    (sem a chave `results`); quando encontra, o summary vem dentro de cada run.
    """
    out: list[dict[str, Any]] = []
    for run in _runs(payload):
        s = run.get("summary")
        if isinstance(s, dict):
            out.append(s)
        elif "resource_count" in run:  # summary "cru", sem results
            out.append(run)
    return out


def _evaluated(payload: Any) -> int:
    """Quantos controles o checkov REALMENTE avaliou (passed + failed + skipped)."""
    total = 0
    for s in _summaries(payload):
        for k in ("passed", "failed", "skipped"):
            v = s.get(k)
            if isinstance(v, int):
                total += v
    return total


def _parsing_errors(payload: Any) -> int:
    """Arquivos IaC que o checkov não conseguiu parsear — logo, NÃO avaliou."""
    total = 0
    for s in _summaries(payload):
        v = s.get("parsing_errors")
        if isinstance(v, int):
            total += v
    return total


class CheckovAdapter:
    name = "checkov"

    def __init__(self, bin_path: str | None = None, git_bin: str | None = None) -> None:
        self.bin = bin_path or shutil.which("checkov") or "checkov"
        self.git_bin = git_bin or shutil.which("git") or "git"
        self._tasks: dict[str, asyncio.Task[tuple[int, Path]]] = {}
        self._workdirs: dict[str, Path] = {}

    async def health(self) -> bool:
        try:
            p = await asyncio.create_subprocess_exec(
                self.bin,
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
            raise ValueError(f"checkov só suporta REPO, recebi {target.asset_type}")

        workdir = Path(tempfile.mkdtemp(prefix="cai-checkov-"))
        out_path = workdir / "out.json"
        framework = options.get("framework")  # ex: "terraform" "kubernetes" "dockerfile"
        depth = str(options.get("clone_depth", 1))

        # Diretório local já presente (path) vs. URL de repo a clonar.
        local_dir = Path(target.value)
        use_local = local_dir.is_dir()
        scan_dir = local_dir if use_local else (workdir / "repo")

        async def _run() -> tuple[int, Path]:
            if not use_local:
                clone = await asyncio.create_subprocess_exec(
                    self.git_bin,
                    "clone",
                    "--quiet",
                    "--depth",
                    depth,
                    target.value,
                    str(scan_dir),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await clone.communicate()
                if clone.returncode != 0:
                    log.error("checkov.clone_failed", err=stderr.decode(errors="replace")[:500])
                    return clone.returncode or 1, out_path

            cmd = [
                self.bin,
                "-d",
                str(scan_dir),
                "-o",
                "json",
                "--quiet",
                # --soft-fail: achar misconfig NÃO é erro de execução. Sem isto o
                # checkov sai 1 com achados, e o `poll` (que agora lê o rc) marcaria
                # FAILED justamente quando o scanner funcionou.
                "--soft-fail",
            ]
            if framework:
                cmd.extend(["--framework", str(framework)])

            log.info("checkov.exec", cmd=cmd)
            with out_path.open("wb") as f:
                p = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=f,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await p.communicate()
            rc = p.returncode or 0
            if rc != 0:
                log.error("checkov.exec_failed", rc=rc, err=stderr.decode(errors="replace")[:500])
            return rc, out_path

        native_id = str(uuid4())
        self._workdirs[native_id] = workdir
        self._tasks[native_id] = asyncio.create_task(_run())
        return ScanHandle(
            adapter=self.name,
            native_id=native_id,
            metadata={"repo": target.value, "report": str(out_path), "local": use_local},
        )

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        task = self._tasks.get(handle.native_id)
        if task is None:
            return ScanStatus.FAILED
        if not task.done():
            return ScanStatus.RUNNING
        # Ler o resultado é o que separa "terminou" de "deu certo". Antes daqui o
        # poll devolvia DONE só por `task.done()`: um clone que falhava fechava o
        # scan como concluído e com zero achados.
        rc, _ = task.result()
        return ScanStatus.DONE if rc == 0 else ScanStatus.FAILED

    async def cleanup(self, handle: ScanHandle) -> None:
        from orchestrator.adapters._cleanup import cleanup_subprocess_handle

        await cleanup_subprocess_handle(
            native_id=handle.native_id,
            tasks=self._tasks,  # type: ignore[arg-type]
            output_paths=self._workdirs,  # dir: o helper detecta is_dir()
            adapter_name=self.name,
        )

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        task = self._tasks.get(handle.native_id)
        if task is None or not task.done():
            raise ScanIntegrityError("checkov: fetch_results sem execução concluída.")
        _, path = task.result()

        if not path.exists():
            raise ScanIntegrityError(
                "checkov não escreveu o arquivo de saída: o scan não produziu "
                "resultado. Zero achados aqui NÃO significa IaC sem problema."
            )
        texto = path.read_text(encoding="utf-8").strip()
        if not texto:
            # Exatamente o que o checkov faz quando o diretório não existe: sai 0 e
            # não escreve nada. Era a saída silenciosa do bug do alvo-URL.
            raise ScanIntegrityError(
                "checkov terminou com saída VAZIA — diretório inexistente ou execução "
                "interrompida. Não houve avaliação de IaC."
            )
        try:
            data = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ScanIntegrityError(
                f"saída do checkov não é JSON válido ({e}): resultado não confiável."
            ) from e

        if _evaluated(data) == 0 and _parsing_errors(data) > 0:
            raise ScanIntegrityError(
                f"checkov não avaliou NENHUM controle e falhou ao parsear "
                f"{_parsing_errors(data)} arquivo(s) IaC: cobertura zero, não alvo limpo."
            )

        log.info(
            "checkov.fetch_ok",
            avaliados=_evaluated(data),
            parsing_errors=_parsing_errors(data),
        )
        return RawResults(adapter=self.name, payload=data)

    async def normalize(self, raw: RawResults) -> list[Finding]:
        findings: list[Finding] = []
        placeholder = uuid4()

        for run in _runs(raw.payload):
            results = run.get("results") or {}
            failed = results.get("failed_checks") or []
            for check in failed:
                sev_str = (check.get("severity") or "MEDIUM").upper()
                severity = _CHECKOV_SEVERITY.get(sev_str, Severity.MEDIUM)
                file_path = check.get("file_path", "")
                linhas = check.get("file_line_range") or [None]
                start_line = linhas[0] if linhas else None

                target = Target(
                    asset_type=AssetType.REPO,
                    value=f"{file_path}:{start_line}" if start_line else file_path,
                )

                findings.append(
                    Finding(
                        scan_id=placeholder,
                        target=target,
                        source_tool=self.name,
                        source_rule_id=check.get("check_id"),
                        title=f"{check.get('check_id')}: {check.get('check_name')}",
                        description=(check.get("description") or "")[:2000],
                        severity=severity,
                        confidence=Confidence.FIRM,
                        evidence=[
                            Evidence(
                                description=f"resource={check.get('resource')}",
                                snippet=(check.get("code_block") or "")[:400]
                                if isinstance(check.get("code_block"), str)
                                else None,
                            )
                        ],
                        remediation=check.get("guideline"),
                    )
                )

        # Parse error = arquivo NÃO avaliado. Um relatório que some com isso deixa o
        # leitor concluir que a IaC inteira foi verificada. Vira achado INFO para
        # aparecer no relatório e no bundle, não só num log que ninguém lê.
        erros = _parsing_errors(raw.payload)
        if erros:
            findings.append(
                Finding(
                    scan_id=placeholder,
                    target=Target(asset_type=AssetType.REPO, value="(cobertura)"),
                    source_tool=self.name,
                    source_rule_id="checkov-parsing-errors",
                    title=f"Cobertura IaC incompleta: {erros} arquivo(s) não parsearam",
                    description=(
                        f"O checkov falhou ao interpretar {erros} arquivo(s) de IaC. "
                        "Esses arquivos NÃO foram avaliados — nenhum controle rodou sobre "
                        "eles, então a ausência de achados neles não indica conformidade. "
                        "Verifique sintaxe (HCL/YAML/JSON) e variáveis não resolvidas."
                    ),
                    severity=Severity.INFO,
                    confidence=Confidence.CERTAIN,
                    evidence=[Evidence(description=f"summary.parsing_errors={erros}")],
                    remediation="Corrija os arquivos e rode de novo para obter cobertura completa.",
                )
            )

        log.info("checkov.normalize_done", findings=len(findings), parsing_errors=erros)
        return findings
