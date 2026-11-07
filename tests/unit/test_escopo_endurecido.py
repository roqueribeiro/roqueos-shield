"""Escopo e opções de scanner, depois da revisão de segurança de 07/11/2026.

Cada caso aqui passava antes: medido rodando o validador com LAB_ONLY=true e allowlist
vazia, e montando o argv do nmap a partir de `options`.
"""

from __future__ import annotations

import pytest

from orchestrator.config import settings
from orchestrator.domain import target_validator as tv
from orchestrator.domain.opcoes import OpcaoRecusada, opcoes_seguras


@pytest.fixture
def fechado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")


@pytest.mark.parametrize(
    ("valor", "tipo"),
    [
        ("127.0.0.1:6379/tcp", "port"),  # o Redis do próprio container
        ("169.254.169.254:80/tcp", "port"),
        ("[::1]:8080/tcp", "port"),
        ("http://127.0.0.1:8090\\@example.com/", "url"),  # WHATWG lê 127.0.0.1
        ("http://example.com /", "url"),
        ("http://100.64.0.1/", "url"),  # CGNAT / Tailscale
        ("http://198.18.0.1/", "url"),
        ("http://[64:ff9b::7f00:1]/", "url"),  # NAT64 de 127.0.0.1
        ("http://[2002:7f00:1::]/", "url"),  # 6to4 de 127.0.0.1
    ],
)
def test_recusado(fechado: None, valor: str, tipo: str) -> None:
    with pytest.raises(tv.TargetValidationError):
        tv.validate_target_value(valor, asset_type=tipo)


def test_porta_publica_passa(fechado: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tv, "_resolve_host_ips", lambda h: ["93.184.216.34"])
    assert tv.validate_target_value("example.com:443/tcp", asset_type="port")


def test_nome_liberado_que_passa_a_resolver_loopback_e_recusado(
    fechado: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Liberado quando resolvia para a rede da casa...
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "lab.atacante.test")
    monkeypatch.setattr(tv, "_resolve_host_ips", lambda h: ["192.168.1.50"])
    tv.validate_target_value("http://lab.atacante.test/", asset_type="url")
    # ...e depois do rebinding.
    for ip in ("127.0.0.1", "169.254.169.254", "64:ff9b::7f00:1", "::ffff:169.254.169.254"):
        monkeypatch.setattr(tv, "_resolve_host_ips", lambda h, ip=ip: [ip])
        with pytest.raises(tv.AlvoForaDoEscopo):
            tv.validate_target_value("http://lab.atacante.test/", asset_type="url")


def test_metadata_nem_com_lab_only_desligado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", False)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "169.254.169.254")
    with pytest.raises(tv.AlvoForaDoEscopo):
        tv.validate_target_value("http://169.254.169.254/latest/", asset_type="url")


def test_loopback_so_com_o_proprio_endereco_na_allowlist(fechado: None) -> None:
    with pytest.raises(tv.AlvoForaDoEscopo):
        tv.validate_target_value("http://127.0.0.1:3000/", asset_type="url")
    settings.TARGET_ALLOWLIST = "127.0.0.1"
    assert tv.validate_target_value("http://127.0.0.1:3000/", asset_type="url")


# ------------------ options ------------------


@pytest.mark.parametrize(
    "opcoes",
    [
        {"nmap": {"nmap_args": ["--script", "/var/x.nse", "169.254.169.254"]}},
        {"nmap": {"nmap_args": ["-oN", "/data/secrets/APP_TOKEN"]}},
        {"nuclei": {"templates": ["/var/evil.yaml"]}},
        {"semgrep": {"config": ["/etc/passwd"]}},
        {"semgrep": {"config": ["https://evil.example/rules.yml"]}},
        {"zap": {"active": "sim"}},
        {"zap": {"max_children": 10_000}},
        {"nuclei": {"severity": "low,-t /tmp"}},
        {"scanner_inventado": {}},
        {"censys": {"query": "-flag"}},
    ],
)
def test_opcao_perigosa_recusada(opcoes: dict) -> None:
    with pytest.raises(OpcaoRecusada):
        opcoes_seguras(opcoes)


def test_opcoes_legitimas_passam() -> None:
    assert opcoes_seguras(
        {
            "zap": {"active": True, "ajax": True, "max_children": "10"},
            "nuclei": {"rate_limit": 50, "severity": "high,critical"},
            "semgrep": {"config": ["p/default", "auto"]},
            "trivy": {"severity": ["HIGH", "critical"]},
        }
    ) == {
        "zap": {"active": True, "ajax": True, "max_children": 10},
        "nuclei": {"rate_limit": 50, "severity": "high,critical"},
        "semgrep": {"config": ["p/default", "auto"]},
        "trivy": {"severity": "high,critical"},
    }


# ------------------ pela API ------------------

from httpx import AsyncClient  # noqa: E402

from tests.unit.test_conta_e_settings_api import SENHA, _setup, cliente  # noqa: E402, F401


async def test_api_recusa_opcao_livre_e_openapi_fora_do_escopo(
    cliente: AsyncClient,  # noqa: F811
    fechado: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _setup(cliente)
    monkeypatch.setattr(tv, "_resolve_host_ips", lambda h: ["93.184.216.34"])
    csrf = {"X-RoqueShield": "1"}
    r = await cliente.post(
        "/targets", json={"asset_type": "url", "value": "https://app.example.com/"}, headers=csrf
    )
    assert r.status_code == 201, r.text
    alvo = r.json()["id"]

    r = await cliente.post(
        "/scans",
        json={"target_id": alvo, "options": {"nmap": {"nmap_args": ["-oN", "/data/x"]}}},
        headers=csrf,
    )
    assert r.status_code == 422 and "nmap_args" in r.text

    r = await cliente.post(
        "/scans",
        json={"target_id": alvo, "auth": {"openapi_url": "http://169.254.169.254/latest/"}},
        headers=csrf,
    )
    assert r.status_code == 403 and "openapi_url" in r.text


async def test_setup_errado_tem_freio(cliente: AsyncClient) -> None:  # noqa: F811
    corpo = {"email": "a@x.com", "password": SENHA, "setup_code": "errado"}
    for _ in range(5):
        r = await cliente.post("/setup", json=corpo)
        assert r.status_code == 403
    r = await cliente.post("/setup", json=corpo)
    assert r.status_code == 429


async def test_usuario_criado_com_maiuscula_entra(cliente: AsyncClient) -> None:  # noqa: F811
    await _setup(cliente)
    r = await cliente.post(
        "/users",
        json={"email": "Ana@Exemplo.com", "role": "viewer", "password": "senha-da-ana-123"},
        headers={"X-RoqueShield": "1"},
    )
    assert r.status_code in (200, 201), r.text
    cliente.cookies.clear()
    r = await cliente.post(
        "/auth/session", json={"email": "ana@exemplo.com", "password": "senha-da-ana-123"}
    )
    assert r.status_code == 200, r.text


def test_registry_de_imagem_passa_pela_guarda_dura(monkeypatch: pytest.MonkeyPatch) -> None:
    # Revisão do PR #20: o tipo image saía antes da guarda dura.
    monkeypatch.setattr(settings, "LAB_ONLY", False)
    for valor in ("169.254.169.254/x/y:latest", "127.0.0.1:5000/x/y:latest"):
        with pytest.raises(tv.TargetValidationError):
            tv.validate_target_value(valor, asset_type="image")
    assert tv.validate_target_value("nginx:1.27-alpine", asset_type="image")


def test_nat64_de_loopback_nao_se_libera(fechado: None, monkeypatch: pytest.MonkeyPatch) -> None:
    for embrulho in ("64:ff9b::7f00:1", "64:ff9b:1::7f00:1"):
        monkeypatch.setattr(settings, "TARGET_ALLOWLIST", embrulho)
        with pytest.raises(tv.AlvoForaDoEscopo) as e:
            tv.validate_target_value(f"http://[{embrulho}]/", asset_type="url")
        assert tv.liberavel_pela_tela(e.value) is False
    monkeypatch.setattr(settings, "LAB_ONLY", False)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    with pytest.raises(tv.AlvoForaDoEscopo):
        tv.validate_target_value("http://[64:ff9b:1::7f00:1]/", asset_type="url")
