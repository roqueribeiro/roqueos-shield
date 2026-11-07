"""Logs ao vivo e telemetria do container standalone, sem Docker.

O que importa provar: (1) credencial não chega ao Redis, (2) Redis fora do ar não
derruba o processo nem some com o log local, (3) a telemetria lê o /proc de verdade e
não inventa número quando não há /proc.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.api import deps
from orchestrator.api.routers import system as system_router
from orchestrator.domain.roles import Role
from orchestrator.main import app
from orchestrator.standalone import logtee, telemetria


class _RedisFalso:
    def __init__(self, quebrado: bool = False) -> None:
        self.quebrado = quebrado
        self.itens: list[tuple[str, dict[str, str]]] = []

    def xadd(self, chave: str, campos: dict[str, str], **_: Any) -> None:
        if self.quebrado:
            raise ConnectionError("redis fora")
        self.itens.append((chave, campos))


def test_tee_redige_credencial_antes_do_redis() -> None:
    r = _RedisFalso()
    out = io.StringIO()
    tee = logtee.Tee("worker", r, out)
    tee.linha("GET /x Authorization: Bearer abc.def.ghi X-API-Token: tok-123456\n")
    assert r.itens and r.itens[0][0] == "rs:logs:worker"
    guardado = r.itens[0][1]["text"]
    assert "abc.def.ghi" not in guardado
    assert "tok-123456" not in guardado


def test_tee_com_redis_fora_segue_no_stdout() -> None:
    out = io.StringIO()
    tee = logtee.Tee("worker", _RedisFalso(quebrado=True), out)
    tee.linha("primeira\n")
    tee.linha("segunda\n")
    assert out.getvalue() == "primeira\nsegunda\n"


def _proc_falso(raiz: Path, pid: int, cmd: list[str], utime: int, rss_kb: int) -> None:
    d = raiz / str(pid)
    d.mkdir(parents=True)
    (d / "cmdline").write_bytes(b"\0".join(c.encode() for c in cmd) + b"\0")
    campos = ["S"] + ["0"] * 10 + [str(utime), "0"] + ["0"] * 30
    (d / "stat").write_text(f"{pid} (python) " + " ".join(campos))
    (d / "status").write_text(f"Name:\tpython\nVmRSS:\t{rss_kb} kB\n")


def test_servicos_le_o_proc(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _proc_falso(proc, 10, ["python", "-m", "uvicorn", "orchestrator.main:app"], 100, 2048)
    _proc_falso(proc, 11, ["arq", "orchestrator.jobs.queue.WorkerSettings"], 50, 4096)
    cg = tmp_path / "cg"
    cg.mkdir()
    (cg / "memory.max").write_text("1073741824\n")
    r = telemetria.servicos(proc=proc, cgroup=cg, janela=0.01)
    por = {c["service"]: c for c in r["containers"]}
    assert r["disponivel"] is True
    assert por["orchestrator"]["state"] == "running"
    assert por["orchestrator"]["memUsage"] == 2048 * 1024
    assert por["worker"]["memUsage"] == 4096 * 1024
    assert por["redis"]["state"] == "exited"
    assert por["redis"]["memUsage"] is None
    assert por["worker"]["memLimit"] == 1073741824


def test_sem_proc_nao_inventa_numero(tmp_path: Path) -> None:
    r = telemetria.servicos(proc=tmp_path / "nao-existe", cgroup=tmp_path, janela=0.01)
    assert r == {"containers": [], "at": r["at"], "disponivel": False}
    assert telemetria.uso_do_container(cgroup=tmp_path / "nada", janela=0.01) == {
        "disponivel": False
    }


def test_uso_do_container_pelo_cgroup(tmp_path: Path) -> None:
    (tmp_path / "cpu.stat").write_text("usage_usec 1000\n")
    (tmp_path / "memory.current").write_text("536870912\n")
    (tmp_path / "memory.max").write_text("1073741824\n")
    u = telemetria.uso_do_container(cgroup=tmp_path, janela=0.01)
    assert u["disponivel"] is True
    assert u["memPercent"] == 50.0


class _RedisAsyncFalso:
    def __init__(
        self, itens: list[tuple[bytes, dict[bytes, bytes]]] | None, quebrado: bool = False
    ) -> None:
        self.itens = itens or []
        self.quebrado = quebrado

    async def xrevrange(self, chave: str, count: int) -> list[tuple[bytes, dict[bytes, bytes]]]:
        if self.quebrado:
            raise ConnectionError("fora")
        return list(reversed(self.itens))[:count]


def _cliente_http(role: Role) -> AsyncClient:
    app.dependency_overrides[deps.get_principal] = lambda: deps.Principal(
        id="a", email="a@x", role=role, is_service=False
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.fixture(autouse=True)
def _limpa() -> object:
    yield
    app.dependency_overrides.clear()


async def test_logs_em_ordem_com_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    itens = [
        (f"{i}-0".encode(), {b"ts": f"2026-11-06T00:00:0{i}".encode(), b"text": f"l{i}".encode()})
        for i in range(5)
    ]
    monkeypatch.setattr(system_router, "_cliente", lambda: _RedisAsyncFalso(itens))
    async with _cliente_http(Role.ADMIN) as c:
        r = await c.get("/system/logs/worker", params={"tail": 3})
    corpo = r.json()
    assert [ln["text"] for ln in corpo["lines"]] == ["l2", "l3", "l4"]
    assert corpo["truncated"] is True


async def test_logs_redis_fora_diz_indisponivel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system_router, "_cliente", lambda: _RedisAsyncFalso(None, quebrado=True))
    async with _cliente_http(Role.ADMIN) as c:
        r = await c.get("/system/logs/worker")
    assert r.status_code == 200
    assert r.json()["available"] is False


async def test_logs_servico_invalido_e_viewer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system_router, "_cliente", lambda: _RedisAsyncFalso([]))
    async with _cliente_http(Role.ADMIN) as c:
        assert (await c.get("/system/logs/..%2Fetc")).status_code in (400, 404)
        assert (await c.get("/system/logs/WORKER")).status_code == 400
    async with _cliente_http(Role.VIEWER) as c:
        assert (await c.get("/system/logs/worker")).status_code == 403
