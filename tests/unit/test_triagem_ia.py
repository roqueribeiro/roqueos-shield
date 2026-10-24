"""GOAL-SHIELD-03: a triagem IA que zerava em produção, o cost map e o Phoenix.

Medido nos logs da frota em 23/10/2026: no acemagic, `ai.triage_done triaged=0` com
559 linhas de `ai.triage_missing`, porque o modelo local (`qwen3.6-35b-200k`, com
`api_base` próprio) não tinha prefixo de provedor e o litellm recusava cada lote; na
Hetzner, chave Anthropic ausente. Em nenhum dos dois o relatório dizia por quê.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from orchestrator.ai import analyzer, gateway
from orchestrator.ai.agentic.tracing import setup_phoenix
from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Finding,
    Severity,
    Target,
)


def _achado(titulo: str, sev: Severity = Severity.HIGH) -> Finding:
    return Finding(
        scan_id=uuid4(),
        target=Target(asset_type=AssetType.URL, value="https://app.example"),
        source_tool="zap",
        title=titulo,
        description="d",
        severity=sev,
        confidence=Confidence.FIRM,
        remediation=f"corrigir {titulo}",
    )


def _resposta(fid: str, sev: str = "medium") -> dict:
    return {"finding_id": fid, "adjusted_severity": sev, "rationale": "ok"}


@pytest.fixture
def llm(monkeypatch):
    """LLM falsa: cada chamada devolve o próximo item da fila (ou levanta)."""
    fila: list = []

    async def complete_json(messages, **kwargs):
        resposta = fila.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr(analyzer, "complete_json", complete_json)
    return fila


async def test_id_exato_maiusculo_ou_truncado_casa_com_o_achado(llm):
    a, b, c = _achado("a"), _achado("b"), _achado("c")
    llm.append(
        {
            "triages": [
                _resposta(str(a.id), "low"),
                _resposta(str(b.id).upper(), "critical"),
                _resposta(str(c.id)[:13], "info"),
            ]
        }
    )
    await analyzer.triage_batch([a, b, c], batch_size=6)
    assert [(f.ai_triage.adjusted_severity, f.ai_triage.model_used) for f in (a, b, c)] == [
        (Severity.LOW, analyzer.settings.LLM_MODEL),
        (Severity.CRITICAL, analyzer.settings.LLM_MODEL),
        (Severity.INFO, analyzer.settings.LLM_MODEL),
    ]


async def test_ids_inventados_mas_um_por_achado_vale_a_ordem(llm):
    a, b = _achado("a"), _achado("b")
    llm.append({"triages": [_resposta("1", "low"), _resposta("2", "critical")]})
    await analyzer.triage_batch([a, b])
    assert [a.ai_triage.adjusted_severity, b.ai_triage.adjusted_severity] == [
        Severity.LOW,
        Severity.CRITICAL,
    ]


async def test_lote_que_falha_vira_triagem_deterministica_com_o_motivo(llm):
    a, b = _achado("a", Severity.MEDIUM), _achado("b", Severity.HIGH)
    llm.append(RuntimeError("litellm.BadRequestError: LLM Provider NOT provided\ndetalhe"))
    await analyzer.triage_batch([a, b])
    for f, sev in ((a, Severity.MEDIUM), (b, Severity.HIGH)):
        t = f.ai_triage
        assert t.model_used == analyzer.TRIAGEM_DETERMINISTICA
        assert t.adjusted_severity == sev  # a do scanner, sem inventar
        assert t.suggested_remediation == f.remediation
        assert "LLM Provider NOT provided" in t.rationale
        assert "detalhe" not in t.rationale  # só a primeira linha do erro
        assert "sem análise contextual" in t.rationale


async def test_achado_que_a_ia_esqueceu_tambem_recebe_a_deterministica(llm):
    a, b, c = _achado("a"), _achado("b"), _achado("c")
    llm.append({"triages": [_resposta(str(a.id), "low"), _resposta(str(b.id), "low")]})
    await analyzer.triage_batch([a, b, c])
    assert [f.ai_triage.model_used for f in (a, b, c)] == [
        analyzer.settings.LLM_MODEL,
        analyzer.settings.LLM_MODEL,
        analyzer.TRIAGEM_DETERMINISTICA,
    ]
    assert "não devolveu" in c.ai_triage.rationale


def test_modelo_cru_em_endpoint_proprio_vira_openai_compat():
    assert gateway._routable_model("qwen3.6-35b-200k", "https://api.dgxsparks.com/v1") == (
        "openai/qwen3.6-35b-200k"
    )
    # provedor conhecido fica como está, com ou sem api_base
    assert gateway._routable_model("openai/qwen3", "http://lm:1234/v1") == "openai/qwen3"
    assert gateway._routable_model("ollama/llama3", "http://ollama:11434") == "ollama/llama3"
    assert gateway._routable_model("anthropic/claude-opus-4-7", None) == (
        "anthropic/claude-opus-4-7"
    )
    # sem api_base não há para onde mandar o nome cru: não inventa provedor
    assert gateway._routable_model("qwen3.6-35b-200k", None) == "qwen3.6-35b-200k"


def test_cost_map_do_litellm_fica_local():
    assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "True"


def test_phoenix_sem_o_extra_nao_se_anuncia_ligado():
    pytest.importorskip("opentelemetry")  # sem nem isso, o import falha antes
    try:
        import openinference.instrumentation.litellm  # noqa: F401
    except ImportError:
        assert setup_phoenix("http://phoenix:6006/v1/traces") is False
    else:
        pytest.skip("extra tracing instalado neste ambiente")


def test_phoenix_vem_desligado_por_padrao():
    from orchestrator.config import Settings

    assert Settings().PHOENIX_ENABLED is False
