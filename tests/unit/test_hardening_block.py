"""Endurecimento: SEC-06 (caps), SEC-07 (audit mutável), SEC-09 (gate), SEC-11 (OIDC)."""

from __future__ import annotations

from pathlib import Path

import yaml

from orchestrator.config import Settings, audit_is_mutable, insecure_boot_errors

_ROOT = Path(__file__).resolve().parents[2]


def _svc(compose: str, name: str) -> dict:
    data = yaml.safe_load((_ROOT / "docker" / compose).read_text(encoding="utf-8"))
    return data["services"][name]


# --- SEC-06: container não roda com capabilities de sobra ---
def test_orchestrator_and_worker_drop_all_caps() -> None:
    for name in ("orchestrator", "worker"):
        svc = _svc("compose.yml", name)
        assert svc["cap_drop"] == ["ALL"], name
        assert svc["cap_add"] == ["NET_RAW"], name  # nmap precisa; NET_ADMIN não
        assert "no-new-privileges:true" in svc["security_opt"], name


def test_kali_toolbox_drops_all_caps() -> None:
    svc = _svc("compose.scanners.yml", "kali-toolbox")
    assert svc["cap_drop"] == ["ALL"]
    assert svc["cap_add"] == ["NET_RAW"]


# --- SEC-07: trilha mutável é detectada e pode ser proibida ---
def test_sqlite_audit_is_flagged_mutable() -> None:
    assert audit_is_mutable(Settings(DATABASE_URL="sqlite+aiosqlite:///./data/cai.db"))


def test_postgres_audit_not_flagged() -> None:
    assert not audit_is_mutable(Settings(DATABASE_URL="postgresql+asyncpg://u@h/db"))


def test_require_immutable_audit_blocks_sqlite_boot() -> None:
    s = Settings(
        DATABASE_URL="sqlite+aiosqlite:///./x.db",
        REQUIRE_IMMUTABLE_AUDIT=True,
        APP_TOKEN="9f2b7c1e4a6d8f0b2c4e6a8d0f1b3c5e",  # noqa: S106
    )
    assert any("REQUIRE_IMMUTABLE_AUDIT" in e for e in insecure_boot_errors(s))


# --- SEC-09 / SEC-11: gates de código ---
def test_defectdojo_export_requires_scans_run() -> None:
    src = (_ROOT / "orchestrator/api/routers/reports.py").read_text(encoding="utf-8")
    block = src.split("async def export_defectdojo")[1][:300]
    assert "RequireScansRun" in block  # exfil pra sistema externo não é leitura


def test_oidc_email_linking_requires_verified_email() -> None:
    src = (_ROOT / "orchestrator/auth/provisioning.py").read_text(encoding="utf-8")
    assert "email_verified" in src
    assert "if user is None and email and email_verified:" in src
