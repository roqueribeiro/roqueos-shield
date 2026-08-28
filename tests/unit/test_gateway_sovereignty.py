"""SEC-03: fallback local→cloud respeita ALLOW_CLOUD_FALLBACK (soberania de dados)."""

from __future__ import annotations

import pytest

from orchestrator.ai import gateway


class _FakeResp:
    def __init__(self, text: str) -> None:
        msg = type("M", (), {"content": text})()
        self.choices = [type("C", (), {"message": msg})()]
        self.usage = None


async def _noop_persist(**kwargs: object) -> None:
    return None


def _local_primary_cloud_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway.settings, "LLM_API_BASE", "http://localhost:1234/v1")
    monkeypatch.setattr(gateway.settings, "LLM_API_KEY", "lm-studio")  # noqa: S106
    monkeypatch.setattr(gateway.settings, "LLM_FALLBACK_MODEL", "anthropic/claude-haiku-4-5")
    monkeypatch.setattr(gateway, "_persist_ai_run", _noop_persist)


async def test_cloud_fallback_blocked_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _local_primary_cloud_fallback(monkeypatch)
    monkeypatch.setattr(gateway.settings, "ALLOW_CLOUD_FALLBACK", False)
    calls: list[dict] = []

    async def fake_acompletion(**kwargs: object) -> _FakeResp:
        calls.append(kwargs)
        if kwargs.get("api_base"):
            raise TimeoutError("local down")
        return _FakeResp("cloud answer")

    monkeypatch.setattr(gateway, "acompletion", fake_acompletion)
    with pytest.raises(TimeoutError):
        await gateway.complete([{"role": "user", "content": "x"}], model="openai/qwen-local")
    assert all(c.get("api_base") for c in calls)  # nenhuma chamada cloud aconteceu


async def test_cloud_fallback_allowed_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _local_primary_cloud_fallback(monkeypatch)
    monkeypatch.setattr(gateway.settings, "ALLOW_CLOUD_FALLBACK", True)
    calls: list[dict] = []

    async def fake_acompletion(**kwargs: object) -> _FakeResp:
        calls.append(kwargs)
        if kwargs.get("api_base"):
            raise TimeoutError("local down")
        return _FakeResp("cloud answer")

    monkeypatch.setattr(gateway, "acompletion", fake_acompletion)
    out = await gateway.complete([{"role": "user", "content": "x"}], model="openai/qwen-local")
    assert out == "cloud answer"
    assert any(not c.get("api_base") for c in calls)  # o fallback cloud foi exercido
