"""O caminho de quem acabou de instalar: alvo bloqueado explicado e IA sem chave neutra.

Medido no standalone v0.5.0 em 07/11/2026, como um iniciante: `http://localhost:3000`
e `http://host.docker.internal:3000` passavam pelo assistente inteiro, a revisão dizia
"vale qualquer alvo fora das redes bloqueadas", e o último clique dava só "Não foi
possível iniciar o scan". E todo scan sem chave de IA terminava com a aba de IA
vermelha, "a triagem falhou".
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from orchestrator.ai import analyzer
from orchestrator.config import settings
from orchestrator.domain import target_validator as tv
from orchestrator.domain.schemas import AssetType, Confidence, Finding, Severity, Target
from tests.unit.test_conta_e_settings_api import _setup, cliente  # noqa: F401

CSRF = {"X-RoqueShield": "1"}


@pytest.fixture
def escopo_fechado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")


def _bloqueio(valor: str) -> tv.AlvoForaDoEscopo:
    with pytest.raises(tv.AlvoForaDoEscopo) as e:
        tv.validate_target_value(valor, asset_type="url")
    return e.value


# ------------------ alvo fora do escopo, tipado ------------------


def test_localhost_e_o_proprio_container_e_nao_se_libera(escopo_fechado: None) -> None:
    for valor in ("http://localhost:3000", "http://127.0.0.1:3000/", "http://[::1]:8080/"):
        e = _bloqueio(valor)
        assert e.motivo == "rede_local"
        assert e.loopback is True
        assert tv.liberavel_pela_tela(e) is False, valor


def test_rede_da_casa_se_libera(escopo_fechado: None) -> None:
    e = _bloqueio("http://192.168.88.12:8080/")
    assert (e.motivo, e.loopback) == ("rede_local", False)
    assert tv.liberavel_pela_tela(e) is True


def test_metadata_de_nuvem_nao_se_libera(
    escopo_fechado: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = _bloqueio("http://169.254.169.254/latest/meta-data/")
    assert e.motivo == "rede_local"
    assert tv.liberavel_pela_tela(e) is False
    # Pelo nome, mesmo onde ele não resolve (fora da nuvem).
    monkeypatch.setattr(tv, "_resolve_host_ips", lambda h: [])
    e = _bloqueio("http://metadata/computeMetadata/v1/")
    assert e.motivo == "rede_local"
    assert tv.liberavel_pela_tela(e) is False


def test_nome_que_nao_resolve_diz_isso(
    escopo_fechado: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tv, "_resolve_host_ips", lambda h: [])
    e = _bloqueio("http://app-que-nao-existe.interno/")
    assert e.motivo == "nao_resolve"
    assert tv.liberavel_pela_tela(e) is False


def test_o_erro_novo_continua_sendo_o_antigo(escopo_fechado: None) -> None:
    # Quem já trata TargetValidationError (POST /targets, scans, MCP) não muda.
    with pytest.raises(tv.TargetValidationError, match="rede privada/loopback/IMDS"):
        tv.validate_target_value("http://localhost/", asset_type="url")


# ------------------ POST /targets/check ------------------


async def test_check_explica_e_depois_de_liberar_passa(
    cliente: AsyncClient,  # noqa: F811
    escopo_fechado: None,
) -> None:
    await _setup(cliente)

    r = await cliente.post(
        "/targets/check", json={"asset_type": "url", "value": "http://localhost:3000"}, headers=CSRF
    )
    assert r.status_code == 200, r.text
    assert r.json() | {"detalhe": None} == {
        "ok": False,
        "motivo": "rede_local",
        "host": "localhost",
        "loopback": True,
        "liberavel": False,
        "detalhe": None,
    }

    casa = {"asset_type": "url", "value": "http://192.168.88.12:8080/"}
    r = await cliente.post("/targets/check", json=casa, headers=CSRF)
    assert (r.json()["motivo"], r.json()["liberavel"]) == ("rede_local", True)

    s = await cliente.put("/settings/scope", json={"allowlist": ["192.168.88.12"]}, headers=CSRF)
    assert s.status_code == 200, s.text
    r = await cliente.post("/targets/check", json=casa, headers=CSRF)
    assert r.json()["ok"] is True

    r = await cliente.post(
        "/targets/check", json={"asset_type": "url", "value": "--flag"}, headers=CSRF
    )
    assert r.json()["motivo"] == "invalido"


async def test_check_exige_sessao(cliente: AsyncClient) -> None:  # noqa: F811
    r = await cliente.post(
        "/targets/check", json={"asset_type": "url", "value": "https://example.com"}, headers=CSRF
    )
    assert r.status_code == 401


# ------------------ IA sem chave ------------------


def _achado() -> Finding:
    return Finding(
        scan_id=uuid4(),
        target=Target(asset_type=AssetType.URL, value="https://app.example"),
        source_tool="zap",
        title="x",
        description="d",
        severity=Severity.HIGH,
        confidence=Confidence.FIRM,
        remediation="corrigir",
    )


@pytest.fixture
def sem_chave(monkeypatch: pytest.MonkeyPatch) -> None:
    for env in ("LLM_API_BASE", "LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setattr(settings, env, "")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(settings, "LLM_MODEL", "anthropic/claude-opus-4-7")


async def test_sem_chave_a_triagem_nao_chama_a_llm(
    sem_chave: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nao_chame(*a, **k):
        raise AssertionError("a LLM foi chamada sem credencial")

    monkeypatch.setattr(analyzer, "complete_json", nao_chame)
    achados = await analyzer.triage_batch([_achado(), _achado()], skip_severities=set())
    for f in achados:
        assert f.ai_triage is not None
        assert f.ai_triage.model_used == analyzer.TRIAGEM_DETERMINISTICA
        assert "IA não configurada" in f.ai_triage.rationale
        assert f.ai_triage.adjusted_severity == Severity.HIGH


def test_quem_tem_credencial(sem_chave: None, monkeypatch: pytest.MonkeyPatch) -> None:
    assert analyzer.ia_tem_credencial("anthropic/claude-opus-4-7") is False
    assert analyzer.ia_tem_credencial("openai/gpt-5") is False
    # Provedor que o shield não conhece pelo nome: tenta, e o erro vira ai_run.
    assert analyzer.ia_tem_credencial("gemini/gemini-2.5-pro") is True

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant")
    assert analyzer.ia_tem_credencial("anthropic/claude-opus-4-7") is True
    assert analyzer.ia_tem_credencial("openai/gpt-5") is False

    monkeypatch.setattr(settings, "LLM_API_BASE", "http://host.docker.internal:1234/v1")
    assert analyzer.ia_tem_credencial("openai/qwen") is True
