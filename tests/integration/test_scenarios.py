"""Bateria de CENÁRIO: a API de pé, exercitada como o RoqueShield a chama.

Os testes unitários provam funções; este arquivo prova o SISTEMA. Sobe o app
FastAPI com ASGITransport, aplica o schema, e bate nos endpoints com o mesmo
header (`X-API-Token`) que o proxy do roqueos-server injeta — o caminho real de
produção. Existe porque "a suíte está verde" não era resposta suficiente para
levar a ferramenta a um banco.
"""

from __future__ import annotations

import secrets
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.api import deps
from orchestrator.config import settings
from orchestrator.domain.roles import Role
from orchestrator.domain.schemas import AssetType
from orchestrator.jobs.pipelines import resolve_scanners
from orchestrator.main import app
from orchestrator.persistence.db import init_db

# Token forte como o roqueos-server gera (crypto.randomBytes(24) = 48 hex).
_TOKEN = secrets.token_hex(24)


@pytest.fixture(autouse=True)
async def _stack(monkeypatch: pytest.MonkeyPatch, tmp_path):
    # o engine já foi construído no import; o banco de dev serve para o cenário
    monkeypatch.setattr(settings, "APP_TOKEN", _TOKEN)
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "127.0.0.1,juice-shop")
    monkeypatch.setattr(settings, "REPORTS_DIR", tmp_path)
    await init_db()
    yield
    app.dependency_overrides.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


_H = {"X-API-Token": _TOKEN}


# ---------- 1. boot e autenticação (o caminho do proxy) ----------
async def test_health_is_public_and_reports_version() -> None:
    async with _client() as c:
        r = await c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.parametrize(
    ("headers", "esperado"),
    [(_H, 200), (None, 401), ({"X-API-Token": "errado"}, 401)],
)
async def test_service_token_is_the_gate(headers, esperado) -> None:
    async with _client() as c:
        r = await c.get("/scans", headers=headers)
    assert r.status_code == esperado


# ---------- 2. cada tipo de alvo que a UI oferece ----------
@pytest.mark.parametrize(
    ("asset_type", "value"),
    [
        ("url", "http://127.0.0.1:8088"),
        ("host", "127.0.0.1"),
        ("image", "alpine:3.19"),
        ("repo", "https://github.com/roqueribeiro/roqueos-shield"),
    ],
)
async def test_every_asset_type_can_be_registered(asset_type: str, value: str) -> None:
    async with _client() as c:
        r = await c.post("/targets", json={"asset_type": asset_type, "value": value}, headers=_H)
    assert r.status_code in (200, 201), r.text


# ---------- 3. escopo: a trava que protege o cliente ----------
@pytest.mark.parametrize(
    "value",
    [
        "http://169.254.169.254/",  # IMDS da nuvem
        "http://10.0.0.5/",  # rede privada
        "file:///etc/passwd",  # scheme proibido
        "-oN /tmp/x",  # injeção de flag no argv do scanner
    ],
)
async def test_out_of_scope_targets_are_refused(value: str) -> None:
    async with _client() as c:
        r = await c.post("/targets", json={"asset_type": "url", "value": value}, headers=_H)
    assert r.status_code >= 400, f"passou o que devia bloquear: {value}"


# ---------- 4. o bug que fazia o scan devolver ZERO ----------
@pytest.mark.parametrize(
    ("asset_type", "profile", "esperado"),
    [
        (AssetType.IMAGE, "web", ["trivy"]),
        (AssetType.REPO, "web", ["semgrep", "gitleaks", "trufflehog", "trivy", "checkov"]),
        (AssetType.URL, "web", ["zap", "nuclei"]),
        (AssetType.HOST, "network", ["nmap"]),
        (AssetType.URL, "full", ["nmap", "zap", "nuclei"]),
        (AssetType.PORT, "network", ["nmap"]),
    ],
)
def test_scanner_resolution_per_asset_and_profile(asset_type, profile, esperado) -> None:
    assert resolve_scanners(None, asset_type, profile) == esperado


def test_legacy_client_on_image_does_not_zero_the_scan() -> None:
    """O front antigo mandava ['nmap','zap'] em tudo; num IMAGE os dois levantam
    ValueError, o erro era engolido, e o scan fechava com zero findings."""
    assert resolve_scanners(["nmap", "zap"], AssetType.IMAGE, "web") == ["trivy"]


# ---------- 5. RBAC no endpoint mais perigoso ----------
async def test_viewer_cannot_launch_the_agent() -> None:
    app.dependency_overrides[deps.get_principal] = lambda: deps.Principal(
        id="v", email="v@x", role=Role.VIEWER, is_service=False
    )
    async with _client() as c:
        r = await c.post(f"/investigate/{uuid.uuid4()}", json={"dry_run": True})
    assert r.status_code == 403


# ---------- 6. compatibilidade com o RoqueShield ----------
def test_strong_token_from_roqueos_server_passes_the_boot_guard() -> None:
    """O server gera APP_TOKEN com crypto.randomBytes(24). Se o guard do SEC-01
    recusasse esse formato, a stack do RoqueShield não subiria."""
    from orchestrator.config import Settings, insecure_boot_errors

    assert insecure_boot_errors(Settings(APP_TOKEN=secrets.token_hex(24))) == []  # noqa: S106
