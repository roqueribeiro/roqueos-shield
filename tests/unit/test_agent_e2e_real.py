"""E2E REAL da coleira: binário de verdade, processo de verdade, sem mock.

Os outros testes injetam o runner. Este roda o `nmap` de fato contra um servidor
HTTP local, e é o que prova que a cadeia inteira funciona fora do laboratório de
mocks. Pula quando o nmap não está instalado (dev sem a ferramenta).
"""

from __future__ import annotations

import asyncio
import shutil
import sys

import pytest

from orchestrator.ai.agentic.executor import Phase, run_in_kali
from orchestrator.config import settings

pytestmark = pytest.mark.skipif(shutil.which("nmap") is None, reason="nmap não instalado")


@pytest.fixture
async def local_target(monkeypatch: pytest.MonkeyPatch):
    """Sobe um alvo HTTP local e o coloca no escopo autorizado."""
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "127.0.0.1")
    monkeypatch.setattr(settings, "AGENT_EXECUTOR", "local")
    srv = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "http.server",
        "8097",
        "--bind",
        "127.0.0.1",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await asyncio.sleep(1.0)
    yield "127.0.0.1"
    srv.terminate()
    await srv.wait()


async def test_authorized_command_really_runs(local_target: str) -> None:
    d = await run_in_kali(
        ["nmap", "-sV", "-p", "8097", local_target],
        phase=Phase.RECON,
        target=local_target,
        asset_type="host",
        dry_run=False,
        timeout=90,
    )
    assert d.executed and d.exit_code == 0
    assert "8097" in d.stdout and "open" in d.stdout  # o serviço foi visto de verdade


async def test_forbidden_binary_never_runs_for_real(local_target: str) -> None:
    d = await run_in_kali(
        ["hydra", "-l", "admin", local_target],
        phase=Phase.EXPLOIT,
        target=local_target,
        asset_type="host",
        dry_run=False,
    )
    assert not d.allowed and not d.executed and "proibido" in d.reason


async def test_out_of_scope_target_never_runs_for_real(local_target: str) -> None:
    d = await run_in_kali(
        ["nmap", "169.254.169.254"],
        phase=Phase.RECON,
        target="169.254.169.254",
        asset_type="host",
        dry_run=False,
    )
    assert not d.allowed and not d.executed and "fora do escopo" in d.reason


async def test_injection_never_runs_for_real(local_target: str) -> None:
    d = await run_in_kali(
        ["nmap", f"{local_target}; cat /etc/passwd"],
        phase=Phase.RECON,
        target=local_target,
        asset_type="host",
        dry_run=False,
    )
    assert not d.allowed and "metacaractere" in d.reason
