"""SEC-05: /investigate exige scans:run e grava no audit (RBAC + trilha).

Primeiro teste HTTP e2e do repo (ASGITransport) — exercita o gate no nível da rota,
não só a função isolada.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.api import deps
from orchestrator.api.routers import investigate as inv_router
from orchestrator.domain.roles import Role
from orchestrator.main import app


def _principal(role: Role) -> deps.Principal:
    return deps.Principal(id="u1", email="u@x", role=role, is_service=False)


class _FakeSession:
    async def get(self, model: object, ident: object) -> object:
        return object()  # não-None; o investigate_finding real é mockado

    def add(self, obj: object) -> None:
        return None

    async def commit(self) -> None:
        return None


def _client(role: Role) -> AsyncClient:
    app.dependency_overrides[deps.get_principal] = lambda: _principal(role)
    app.dependency_overrides[deps.get_session] = lambda: _FakeSession()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.fixture(autouse=True)
def _clear() -> object:
    yield
    app.dependency_overrides.clear()


async def test_investigate_forbidden_for_viewer() -> None:
    async with _client(Role.VIEWER) as c:
        r = await c.post(f"/investigate/{uuid4()}", json={"dry_run": True})
    assert r.status_code == 403


async def test_investigate_audited_for_operator(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    async def spy_audit(session: object, **kw: object) -> None:
        calls.append(kw)

    async def fake_investigate(finding: object, **kw: object) -> dict:
        return {"transcript": [], "final_assessment": "ok", "trace_url": None}

    monkeypatch.setattr(inv_router, "log_audit_event", spy_audit)
    monkeypatch.setattr("orchestrator.ai.agentic.cai_expert.investigate_finding", fake_investigate)
    async with _client(Role.OPERATOR) as c:
        r = await c.post(f"/investigate/{uuid4()}", json={"dry_run": False})
    assert r.status_code == 200
    assert any(k.get("action") == "investigate.run" for k in calls)
