"""O loop agêntico de verdade — e o gate de profundidade que ele tem que passar.

Antes: `_investigate_with_cai` era `raise NotImplementedError` e toda investigação
caía num único prompt "sem tool use ativo, só raciocínio". Este arquivo é o gate:
se o agente voltar a ser um parecer, estes testes reprovam.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from orchestrator.ai.agentic import cai_expert
from orchestrator.config import settings


def _call(name: str, args: dict, cid: str = "c1") -> SimpleNamespace:
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def _msg(content: str = "", calls: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=calls or [])


class _Finding:
    id = "f1"
    source_tool = "zap"
    title = "SQL injection no login"
    severity = "high"
    payload = {"target": {"value": "juice-shop", "asset_type": "host"}}


@pytest.fixture(autouse=True)
def _lab(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "juice-shop,dvwa")
    monkeypatch.setattr(settings, "AGENT_ENABLED", True)


async def test_agent_is_reachable_not_a_stub() -> None:
    # o ramo do agente era inalcançável (dependia de `import cai`, nunca instalado)
    assert cai_expert._cai_framework_available() is True


async def test_agent_runs_real_tool_calls_and_sees_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """GATE DE PROFUNDIDADE: >=1 tool-call real, e o modelo VÊ a saída."""
    seen: list[str] = []
    turns = iter(
        [
            _msg(
                "vou escanear",
                [
                    _call(
                        "run_command", {"command": ["nmap", "-sV", "juice-shop"], "phase": "recon"}
                    )
                ],
            ),
            _msg(
                "confirmado",
                [
                    _call(
                        "conclude",
                        {"confirmed": True, "assessment": "porta 80 aberta, SQLi validada"},
                        "c2",
                    )
                ],
            ),
        ]
    )

    async def fake_llm(messages, **kw):
        # o feedback da ferramenta tem que chegar de volta ao modelo
        seen.extend(m.get("content", "") for m in messages if m.get("role") == "tool")
        return next(turns)

    async def fake_runner(argv):
        return 0, "80/tcp open http", ""

    monkeypatch.setattr(cai_expert, "complete_with_tools", fake_llm, raising=False)
    monkeypatch.setattr("orchestrator.ai.gateway.complete_with_tools", fake_llm)
    monkeypatch.setattr("orchestrator.ai.agentic.executor._docker_exec", fake_runner)

    out = await cai_expert.investigate_finding(_Finding(), dry_run=False, max_steps=5)

    assert out["engine"] == "agent", "caiu no fallback de parecer"
    assert out["tool_calls"] >= 1, "nenhuma ferramenta foi chamada"
    assert out["commands_executed"] >= 1, "nenhum comando rodou de verdade"
    assert out["confirmed"] is True
    assert any("80/tcp open" in s for s in seen), "o modelo não viu a saída da ferramenta"


async def test_agent_cannot_escape_the_leash(monkeypatch: pytest.MonkeyPatch) -> None:
    """O modelo pede algo proibido: a coleira recusa e o comando NÃO roda."""
    executed = False
    turns = iter(
        [
            _msg(
                "vou brutar",
                [
                    _call(
                        "run_command",
                        {"command": ["hydra", "-l", "admin", "juice-shop"], "phase": "exploit"},
                    )
                ],
            ),
            _msg(
                "ok", [_call("conclude", {"confirmed": False, "assessment": "sem evidência"}, "c2")]
            ),
        ]
    )
    feedback: list[str] = []

    async def fake_llm(messages, **kw):
        feedback.extend(m.get("content", "") for m in messages if m.get("role") == "tool")
        return next(turns)

    async def fake_runner(argv):
        nonlocal executed
        executed = True
        return 0, "", ""

    monkeypatch.setattr("orchestrator.ai.gateway.complete_with_tools", fake_llm)
    monkeypatch.setattr("orchestrator.ai.agentic.executor._docker_exec", fake_runner)

    out = await cai_expert.investigate_finding(_Finding(), dry_run=False, max_steps=5)

    assert not executed, "comando proibido foi executado"
    assert out["commands_executed"] == 0
    assert any("RECUSADO" in f for f in feedback), "o agente não foi informado da recusa"


async def test_dry_run_plans_but_never_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    executed = False
    turns = iter(
        [
            _msg(
                "plano",
                [
                    _call(
                        "run_command", {"command": ["nmap", "-sV", "juice-shop"], "phase": "recon"}
                    )
                ],
            ),
            _msg(
                "fim", [_call("conclude", {"confirmed": False, "assessment": "plano pronto"}, "c2")]
            ),
        ]
    )

    async def fake_llm(messages, **kw):
        return next(turns)

    async def fake_runner(argv):
        nonlocal executed
        executed = True
        return 0, "", ""

    monkeypatch.setattr("orchestrator.ai.gateway.complete_with_tools", fake_llm)
    monkeypatch.setattr("orchestrator.ai.agentic.executor._docker_exec", fake_runner)

    out = await cai_expert.investigate_finding(_Finding(), dry_run=True, max_steps=5)

    assert not executed, "dry_run executou comando"
    assert out["tool_calls"] >= 1 and out["commands_executed"] == 0


async def test_falls_back_to_narrative_when_agent_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AGENT_ENABLED", False)

    async def fake_complete(*a, **kw):
        return "parecer textual"

    monkeypatch.setattr("orchestrator.ai.gateway.complete", fake_complete)
    monkeypatch.setattr(cai_expert, "complete", fake_complete)
    out = await cai_expert.investigate_finding(_Finding(), dry_run=True)
    assert out.get("engine") != "agent"
