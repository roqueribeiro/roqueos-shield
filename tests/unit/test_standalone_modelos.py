from __future__ import annotations

import httpx
import pytest

from orchestrator.config import settings
from orchestrator.standalone import modelos


@pytest.fixture(autouse=True)
def _sem_chaves(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "LLM_API_BASE",
        "LLM_API_KEY",
    ):
        monkeypatch.setattr(settings, k, "")


def _cliente(handler) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_sem_chave_nao_chama_ninguem() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        raise AssertionError("não devia chamar")

    assert await modelos.listar({}, _cliente(h)) == {"groups": [], "errors": []}


async def test_openai_filtra_so_chat_e_ordena() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        assert req.headers["Authorization"] == "Bearer sk-o"
        return httpx.Response(
            200, json={"data": [{"id": "whisper-1"}, {"id": "gpt-4o"}, {"id": "o3"}]}
        )

    r = await modelos.listar({"openaiKey": "sk-o"}, _cliente(h))
    assert r["groups"][0]["models"] == [
        {"id": "openai/gpt-4o", "label": "gpt-4o"},
        {"id": "openai/o3", "label": "o3"},
    ]
    assert r["groups"][0]["live"] is True


async def test_falha_vira_curado_declarado() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "chave"})

    r = await modelos.listar({"anthropicKey": "sk-a"}, _cliente(h))
    assert r["errors"] == ["anthropic"]
    assert r["groups"][0]["live"] is False
    assert r["groups"][0]["models"] == modelos.CURADOS["anthropic"]


async def test_local_aceita_models_ou_data() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        assert str(req.url) == "http://lm:1234/v1/models"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5"}]})

    r = await modelos.listar({"apiBase": "http://lm:1234/v1/"}, _cliente(h))
    assert r["groups"][0]["models"] == [{"id": "qwen2.5", "label": "qwen2.5"}]


async def test_local_vazio_e_erro_sem_curado() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    r = await modelos.listar({"apiBase": "http://lm:1234/v1"}, _cliente(h))
    assert r == {"groups": [], "errors": ["local"]}
