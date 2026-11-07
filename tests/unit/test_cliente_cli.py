"""A CLI `roqueshield`: o contrato de códigos de saída e a credencial guardada.

O que um pipeline de CI precisa poder confiar: cobertura incompleta nunca sai 0.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from orchestrator.cliente import api as apimod
from orchestrator.cliente import cli

runner = CliRunner()


def _scan(**kw: Any) -> dict[str, Any]:
    base = {
        "id": "s1",
        "state": "done",
        "coverage_complete": True,
        "severity_counts": {},
        "target": {"value": "x"},
    }
    return {**base, **kw}


@pytest.mark.parametrize(
    ("scan", "fail_on", "codigo"),
    [
        (_scan(), None, 0),
        (_scan(severity_counts={"high": 2}), None, 0),
        (_scan(severity_counts={"high": 2}), "high", 1),
        (_scan(severity_counts={"critical": 1}), "high", 1),
        (_scan(severity_counts={"medium": 9}), "high", 0),
        # cobertura incompleta com zero achado: 3, nunca 0
        (_scan(coverage_complete=False), None, 3),
        (_scan(coverage_complete=False, severity_counts={"critical": 1}), "high", 3),
        (_scan(state="failed"), None, 3),
    ],
)
def test_codigo_de_saida(scan: dict[str, Any], fail_on: str | None, codigo: int) -> None:
    assert cli.codigo_de_saida(scan, fail_on) == codigo


@pytest.fixture
def servidor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Um shield falso: guarda o que recebeu e responde o que o teste mandar."""
    estado: dict[str, Any] = {"recebido": [], "scan": _scan(), "tokens": {"tok-bom"}}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.headers.get("X-API-Token") not in estado["tokens"]:
            return httpx.Response(401, json={"detail": "X-API-Token inválido"})
        estado["recebido"].append((req.method, req.url.path, req.content.decode() or None))
        p = req.url.path
        if p == "/auth/session":
            return httpx.Response(200, json={"email": "ci@x", "role": "operator"})
        if p == "/targets":
            return httpx.Response(201, json={"id": "t1"})
        if p == "/scans":
            return httpx.Response(201, json={"id": "s1"})
        if p == "/ui/api/scans/s1":
            return httpx.Response(200, json=estado["scan"])
        return httpx.Response(404, json={"detail": "?"})

    original = apimod.Api.__init__

    def init(self: apimod.Api, cfg: apimod.Config, cliente: httpx.Client | None = None) -> None:
        original(
            self, cfg, httpx.Client(base_url=cfg.servidor, transport=httpx.MockTransport(handler))
        )

    monkeypatch.setattr(apimod.Api, "__init__", init)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.delenv("ROQUESHIELD_URL", raising=False)
    monkeypatch.delenv("ROQUESHIELD_TOKEN", raising=False)
    return estado


def test_login_guarda_0600_e_nao_imprime_o_token(servidor: dict[str, Any], tmp_path: Path) -> None:
    r = runner.invoke(cli.app, ["login", "--server", "http://shield:8080/", "--token", "tok-bom"])
    assert r.exit_code == 0, r.output
    assert "tok-bom" not in r.output
    arq = apimod.arquivo_de_config()
    assert stat.S_IMODE(arq.stat().st_mode) == 0o600
    assert json.loads(arq.read_text()) == {"server": "http://shield:8080", "token": "tok-bom"}


def test_login_com_token_errado_nao_grava(servidor: dict[str, Any]) -> None:
    r = runner.invoke(cli.app, ["login", "--server", "http://shield:8080", "--token", "ruim"])
    assert r.exit_code == 2
    assert not apimod.arquivo_de_config().exists()


def test_sem_config_sai_2(servidor: dict[str, Any]) -> None:
    assert runner.invoke(cli.app, ["scan", "list"]).exit_code == 2


def test_scan_wait_incompleto_sai_3(
    servidor: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROQUESHIELD_URL", "http://shield:8080")
    monkeypatch.setenv("ROQUESHIELD_TOKEN", "tok-bom")
    servidor["scan"] = _scan(coverage_complete=False, scanners_skipped={"nuclei": "sem templates"})
    r = runner.invoke(cli.app, ["scan", "start", "http://alvo", "--wait", "--intervalo", "0"])
    assert r.exit_code == 3, r.output
    assert "não rodou: nuclei" in r.output
    metodo, caminho, corpo = servidor["recebido"][1]
    assert (metodo, caminho) == ("POST", "/scans")
    assert json.loads(corpo) == {"target_id": "t1", "profile": "web"}


def test_scan_wait_fail_on_sai_1(servidor: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROQUESHIELD_URL", "http://shield:8080")
    monkeypatch.setenv("ROQUESHIELD_TOKEN", "tok-bom")
    servidor["scan"] = _scan(severity_counts={"high": 1})
    r = runner.invoke(
        cli.app,
        [
            "scan",
            "start",
            "http://alvo",
            "--wait",
            "--fail-on",
            "high",
            "--auth-ref",
            "CHG-1",
            "--intervalo",
            "0",
        ],
    )
    assert r.exit_code == 1, r.output
    assert json.loads(servidor["recebido"][1][2])["authorization_ref"] == "CHG-1"


def test_fail_on_invalido_sai_2(servidor: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROQUESHIELD_URL", "http://shield:8080")
    monkeypatch.setenv("ROQUESHIELD_TOKEN", "tok-bom")
    assert runner.invoke(cli.app, ["scan", "start", "x", "--fail-on", "grave"]).exit_code == 2


def test_dentro_do_container_usa_o_shield_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`docker exec <c> roqueshield status` sem configurar nada: shield local + APP_TOKEN."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    data = tmp_path / "data"
    (data / "secrets").mkdir(parents=True)
    (data / "secrets" / "APP_TOKEN").write_text("tok-local\n")
    cfg = apimod.carregar({"DATA_DIR": str(data), "PORT": "9000"})
    assert cfg == apimod.Config("http://127.0.0.1:9000", "tok-local")
    # Configuração explícita ganha do arquivo local.
    cfg2 = apimod.carregar(
        {"DATA_DIR": str(data), "ROQUESHIELD_URL": "https://x", "ROQUESHIELD_TOKEN": "t"}
    )
    assert cfg2 == apimod.Config("https://x", "t")
    # Compose de produção: APP_TOKEN no ambiente, sem arquivo.
    cfg3 = apimod.carregar({"DATA_DIR": str(tmp_path / "vazio"), "APP_TOKEN": "tok-env"})
    assert cfg3 == apimod.Config("http://127.0.0.1:8080", "tok-env")
    # Sem arquivo nem ambiente, continua sendo erro de configuração.
    with pytest.raises(apimod.SemConfig):
        apimod.carregar({"DATA_DIR": str(tmp_path / "vazio")})
