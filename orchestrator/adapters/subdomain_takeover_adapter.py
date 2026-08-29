"""Subdomain takeover — pipeline subfinder | httpx | nuclei -t takeovers/.

Roda os 3 binários em sequência dentro do kali-toolbox (presume disponíveis no PATH).

O encadeamento era todo em cascata silenciosa: nenhum returncode era lido e cada
etapa só rodava `if arquivo_anterior.exists()`. Subfinder sem rede não escrevia o
arquivo, o httpx não rodava, o nuclei não rodava, e o scan fechava com ZERO achados
— "nenhum subdomínio sequestrável" para um domínio que ninguém enumerou.

E o nuclei ia sem `-duc`/`-ni`: em rede sem egress (o caso normal num banco) ele
tenta atualizar template e falar com o interactsh, e pendura até o timeout de
1800s. Mesmo defeito que já foi consertado no `nuclei_adapter` — aqui tinha voltado
por cópia.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from orchestrator.adapters.base import ScanIntegrityError, read_jsonl
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


class SubdomainTakeoverAdapter:
    name = "subdomain_takeover"

    def __init__(
        self,
        subfinder_bin: str | None = None,
        httpx_bin: str | None = None,
        nuclei_bin: str | None = None,
    ) -> None:
        self.subfinder = subfinder_bin or shutil.which("subfinder") or "subfinder"
        self.httpx = httpx_bin or shutil.which("httpx") or "httpx"
        self.nuclei = nuclei_bin or shutil.which("nuclei") or "nuclei"
        self._tasks: dict[str, asyncio.Task[tuple[int, Path]]] = {}
        self._stats: dict[str, dict[str, int]] = {}
        self._workdirs: dict[str, Path] = {}

    async def health(self) -> bool:
        for b in (self.subfinder, self.httpx, self.nuclei):
            try:
                p = await asyncio.create_subprocess_exec(
                    b,
                    "-version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await p.communicate()
                if p.returncode != 0:
                    return False
            except OSError:  # binário ausente, sem permissão, e os primos do OSError
                return False
        return True

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        if target.asset_type != AssetType.DOMAIN:
            raise ValueError(f"subdomain_takeover espera DOMAIN, recebi {target.asset_type}")

        workdir = Path(tempfile.mkdtemp(prefix="cai-subtake-"))
        subs_path = workdir / "subs.txt"
        live_path = workdir / "live.txt"
        out_path = workdir / "out.jsonl"

        stats: dict[str, int] = {"subdominios": 0, "vivos": 0}

        def _linhas(p: Path) -> int:
            if not p.exists():
                return 0
            return len([x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()])

        async def _run() -> tuple[int, Path]:
            # 1. subfinder — enumera subdomínios
            sf = await asyncio.create_subprocess_exec(
                self.subfinder,
                "-d",
                target.value,
                "-silent",
                "-o",
                str(subs_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err = await sf.communicate()
            if sf.returncode:
                log.error(
                    "subtake.subfinder_failed",
                    rc=sf.returncode,
                    err=err.decode(errors="replace")[:400],
                )
                return sf.returncode, out_path
            stats["subdominios"] = _linhas(subs_path)
            # Zero subdomínios enumerados é resultado LEGÍTIMO (domínio sem filhos
            # públicos): fecha limpo, sem chamar o resto do pipeline.
            if stats["subdominios"] == 0:
                out_path.touch()
                return 0, out_path

            # 2. httpx — filtra os que respondem
            hx = await asyncio.create_subprocess_exec(
                self.httpx,
                "-l",
                str(subs_path),
                "-silent",
                "-o",
                str(live_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err = await hx.communicate()
            if hx.returncode:
                log.error(
                    "subtake.httpx_failed", rc=hx.returncode, err=err.decode(errors="replace")[:400]
                )
                return hx.returncode, out_path
            stats["vivos"] = _linhas(live_path)
            if stats["vivos"] == 0:
                out_path.touch()
                return 0, out_path

            # 3. nuclei -t takeovers/
            nu = await asyncio.create_subprocess_exec(
                self.nuclei,
                "-l",
                str(live_path),
                "-t",
                "http/takeovers/",
                "-jsonl",
                "-o",
                str(out_path),
                "-silent",
                "-no-color",
                # Sem estes dois o nuclei tenta a internet (update de template e
                # interactsh) e pendura até o timeout em rede restrita.
                "-duc",
                "-ni",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err = await nu.communicate()
            if nu.returncode:
                log.error(
                    "subtake.nuclei_failed",
                    rc=nu.returncode,
                    err=err.decode(errors="replace")[:400],
                )
                return nu.returncode, out_path
            out_path.touch()  # nuclei não cria o arquivo quando não há achado
            return 0, out_path

        native_id = str(uuid4())
        self._tasks[native_id] = asyncio.create_task(_run())
        self._workdirs[native_id] = workdir
        self._stats[native_id] = stats
        return ScanHandle(
            adapter=self.name,
            native_id=native_id,
            metadata={"domain": target.value, "workdir": str(workdir)},
        )

    async def cleanup(self, handle: ScanHandle) -> None:
        from orchestrator.adapters._cleanup import cleanup_subprocess_handle

        await cleanup_subprocess_handle(
            native_id=handle.native_id,
            tasks=self._tasks,  # type: ignore[arg-type]
            output_paths=self._workdirs,
            adapter_name=self.name,
        )

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        task = self._tasks.get(handle.native_id)
        if task is None:
            return ScanStatus.FAILED
        if not task.done():
            return ScanStatus.RUNNING
        # Ler o returncode é o que separa "as três etapas rodaram" de "a primeira
        # morreu e as outras duas nem foram chamadas".
        rc, _ = task.result()
        return ScanStatus.DONE if rc == 0 else ScanStatus.FAILED

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        rc, out_path = await self._tasks[handle.native_id]
        if rc:
            raise ScanIntegrityError(
                f"pipeline de takeover terminou com código {rc}: alguma das três "
                "etapas (subfinder/httpx/nuclei) não rodou."
            )
        if not out_path.exists():
            raise ScanIntegrityError(
                "pipeline de takeover não produziu saída: nenhuma etapa foi concluída. "
                "Zero achados aqui NÃO significa domínio sem subdomínio sequestrável."
            )
        gaps: list[str] = []
        items = read_jsonl(out_path, adapter=self.name, gaps=gaps)
        st = self._stats.get(handle.native_id, {})
        log.info("subtake.fetch_ok", achados=len(items), **st)
        return RawResults(adapter=self.name, payload=items, coverage_gaps=gaps)

    async def normalize(self, raw: RawResults) -> list[Finding]:
        findings: list[Finding] = []
        placeholder = uuid4()
        for item in raw.payload:
            url = item.get("matched-at") or item.get("host", "")
            target = Target(asset_type=AssetType.URL, value=url)
            findings.append(
                Finding(
                    scan_id=placeholder,
                    target=target,
                    source_tool=self.name,
                    source_rule_id=item.get("template-id", "takeover"),
                    title=f"Possível subdomain takeover: {url}",
                    description=(
                        f"Template {item.get('template-id')} indica que {url} "
                        "aponta pra serviço terceiro desativado. "
                        "Atacante pode reclamar o recurso e servir conteúdo malicioso "
                        "como se fosse o subdomínio do banco."
                    ),
                    severity=Severity.HIGH,
                    confidence=Confidence.FIRM,
                    evidence=[
                        Evidence(
                            description=f"template={item.get('template-id')}",
                            snippet=(item.get("response") or "")[:400],
                        )
                    ],
                )
            )
        log.info("subdomain_takeover.normalize_done", findings=len(findings))
        return findings
