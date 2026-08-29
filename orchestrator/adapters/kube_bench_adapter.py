"""kube-bench adapter — CIS Kubernetes Benchmark.

Subprocess + JSON output. Roda contra cluster atual (kubeconfig montado).

Silêncio corrigido: sem kubeconfig (ou sem o binário conseguindo falar com o
cluster) o kube-bench escreve saída vazia; o adapter transformava isso em `{}`, o
normalize não achava `Controls`, e o resultado saía como ZERO controles CIS
reprovados — indistinguível de um cluster em conformidade. Num relatório entregue a
auditoria, essa diferença é a que importa.
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


class KubeBenchAdapter:
    name = "kube_bench"

    def __init__(self, bin_path: str | None = None) -> None:
        self.bin = bin_path or shutil.which("kube-bench") or "kube-bench"
        self._tasks: dict[str, asyncio.Task[int]] = {}
        self._outs: dict[str, Path] = {}

    async def health(self) -> bool:
        try:
            p = await asyncio.create_subprocess_exec(
                self.bin,
                "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await p.communicate()
            return p.returncode == 0
        except OSError:  # binário ausente, sem permissão, e os primos do OSError
            return False

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        out_path = Path(tempfile.mkdtemp(prefix="cai-kbench-")) / "out.json"
        targets_arg = options.get("targets", "master,node,etcd,policies")

        cmd = [
            self.bin,
            "run",
            "--targets",
            targets_arg,
            "--json",
        ]

        log.info("kube_bench.start_scan", cmd=cmd)

        async def _run() -> int:
            with out_path.open("wb") as f:
                p = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=f,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, err = await p.communicate()
            rc = p.returncode or 0
            if rc:
                log.error("kube_bench.exec_failed", rc=rc, err=err.decode(errors="replace")[:500])
            return rc

        native_id = str(uuid4())
        self._outs[native_id] = out_path
        self._tasks[native_id] = asyncio.create_task(_run())
        return ScanHandle(
            adapter=self.name,
            native_id=native_id,
            metadata={"cluster": target.value, "targets": targets_arg},
        )

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        task = self._tasks.get(handle.native_id)
        if task is None:
            return ScanStatus.FAILED
        if not task.done():
            return ScanStatus.RUNNING
        # kube-bench sai 0 mesmo com controles reprovados (o `--exit-code` é opt-in).
        # Código != 0 é erro de execução, não achado.
        return ScanStatus.DONE if task.result() == 0 else ScanStatus.FAILED

    async def cleanup(self, handle: ScanHandle) -> None:
        from orchestrator.adapters._cleanup import cleanup_subprocess_handle

        await cleanup_subprocess_handle(
            native_id=handle.native_id,
            tasks=self._tasks,  # type: ignore[arg-type]
            output_paths=self._outs,
            adapter_name=self.name,
        )

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        path = self._outs.get(handle.native_id)
        if path is None or not path.exists():
            raise ScanIntegrityError(
                "kube-bench não escreveu saída: o benchmark não rodou. Zero controles "
                "reprovados aqui NÃO significa cluster em conformidade."
            )
        texto = path.read_text(encoding="utf-8").strip()
        if not texto:
            raise ScanIntegrityError(
                "saída do kube-bench vazia (tipicamente kubeconfig ausente ou cluster "
                "inalcançável): nenhum controle CIS foi avaliado."
            )
        try:
            data = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ScanIntegrityError(
                f"saída do kube-bench não é JSON válido ({e}): resultado não confiável."
            ) from e
        avaliados = _controles_avaliados(data)
        if avaliados == 0:
            raise ScanIntegrityError(
                "kube-bench não avaliou NENHUM controle CIS: cobertura zero, não "
                "conformidade. Verifique kubeconfig, --targets e permissões."
            )
        log.info("kube_bench.fetch_ok", controles_avaliados=avaliados)
        return RawResults(adapter=self.name, payload=data)

    async def normalize(self, raw: RawResults) -> list[Finding]:
        findings: list[Finding] = []
        placeholder = uuid4()

        # kube-bench: { "Controls": [ { "tests": [ { "results": [ ... ] } ] } ] }
        for ctrl in raw.payload.get("Controls", []):
            for test in ctrl.get("tests", []):
                for r in test.get("results", []):
                    status = (r.get("status") or "").upper()
                    if status != "FAIL":
                        continue
                    # kube-bench não tem severity nativo; mapear: scored fail = MEDIUM
                    severity = Severity.MEDIUM if r.get("scored", True) else Severity.LOW
                    target = Target(
                        asset_type=AssetType.K8S_RESOURCE,
                        value=r.get("test_number", "?"),
                    )
                    findings.append(
                        Finding(
                            scan_id=placeholder,
                            target=target,
                            source_tool=self.name,
                            source_rule_id=r.get("test_number", "?"),
                            title=f"CIS {r.get('test_number')}: {r.get('test_desc', '')}",
                            description=r.get("audit", "") or "",
                            severity=severity,
                            confidence=Confidence.FIRM,
                            evidence=[
                                Evidence(
                                    description=f"actual: {r.get('actual_value', '')[:300]}",
                                    snippet=r.get("expected_result"),
                                )
                            ],
                            remediation=r.get("remediation"),
                        )
                    )
        log.info("kube_bench.normalize_done", findings=len(findings))
        return findings


def _controles_avaliados(data: Any) -> int:
    """Quantos resultados de controle o kube-bench realmente produziu.

    Sem este contador, "0 FAIL" tem dois significados opostos: cluster conforme, ou
    benchmark que não rodou. Um relatório de compliance não pode confundir os dois.
    """
    if not isinstance(data, dict):
        return 0
    total = 0
    for ctrl in data.get("Controls") or []:
        if not isinstance(ctrl, dict):
            continue
        for teste in ctrl.get("tests") or []:
            if isinstance(teste, dict):
                total += len(teste.get("results") or [])
    return total
