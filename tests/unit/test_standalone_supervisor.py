"""O supervisor decide pelo ambiente, reinicia com espera crescente e para limpo."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from orchestrator.standalone import supervisor as sup


def test_ambiente_vence_e_completa(tmp_path: Path) -> None:
    env = sup.ambiente_base({"REDIS_URL": "redis://fora:6379/0", "PATH": ""}, tmp_path)
    assert env["REDIS_URL"] == "redis://fora:6379/0"
    assert env["DATABASE_URL"].endswith(str(tmp_path / "shield.db"))
    assert env["TRIVY_SERVER_URL"] == ""
    assert "ZAP_BASE_URL" not in env  # sem zap.sh no PATH, não inventa ZAP


def test_redis_de_fora_nao_sobe_o_embutido(tmp_path: Path) -> None:
    nomes = [s.nome for s in sup.servicos({"REDIS_URL": "redis://fora:6379/0"}, tmp_path)]
    assert nomes == ["orchestrator", "worker"]


def test_tudo_embutido(tmp_path: Path) -> None:
    env = {"REDIS_URL": sup.REDIS_LOCAL, "ZAP_BASE_URL": sup.ZAP_LOCAL, "ZAP_API_KEY": "k"}
    lista = sup.servicos(env, tmp_path)
    assert [s.nome for s in lista] == ["redis", "zap", "orchestrator", "worker"]
    redis = lista[0].argv
    assert redis[redis.index("--bind") + 1] == "127.0.0.1"
    zap = lista[1].argv
    assert zap[zap.index("-host") + 1] == "127.0.0.1"
    # A chave vai por arquivo 0600, nunca no cmdline (legível por qualquer processo).
    assert not any("k" == a.split("=")[-1] for a in zap), zap
    arq = Path(zap[zap.index("-configfile") + 1])
    assert "api.key=k" in arq.read_text()
    assert arq.stat().st_mode & 0o777 == 0o600


def test_espera_cresce_e_tem_teto() -> None:
    assert [sup.espera(n) for n in (1, 2, 3, 4)] == [1.0, 2.0, 4.0, 8.0]
    assert sup.espera(50) == sup.ESPERA_MAX


async def test_reinicia_quem_cai_e_para_no_sinal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sup, "espera", lambda n: 0.01)
    svc = sup.Servico("teste", [sys.executable, "-c", "print('oi')"])
    svc.env = {}
    parar = asyncio.Event()
    tarefa = asyncio.create_task(sup._rodar(svc, None, parar))
    for _ in range(200):
        if svc.reinicios >= 3:
            break
        await asyncio.sleep(0.02)
    parar.set()
    await asyncio.wait_for(tarefa, timeout=5)
    assert svc.reinicios >= 3


async def test_binario_ausente_nao_derruba(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sup, "espera", lambda n: 0.01)
    svc = sup.Servico("fantasma", ["/nao/existe/binario"])
    parar = asyncio.Event()
    tarefa = asyncio.create_task(sup._rodar(svc, None, parar))
    await asyncio.sleep(0.1)
    parar.set()
    await asyncio.wait_for(tarefa, timeout=5)
    assert svc.reinicios >= 1


async def test_encerrar_termina_os_filhos() -> None:
    svc = sup.Servico("dorme", [sys.executable, "-c", "import time; time.sleep(30)"])
    svc.processo = await asyncio.create_subprocess_exec(*svc.argv)
    await sup._encerrar([svc], prazo=5)
    assert svc.processo.returncode is not None


def test_shield_services_restringe(tmp_path: Path) -> None:
    env = {"REDIS_URL": "redis://r:6379/0", "SHIELD_SERVICES": "worker"}
    assert [s.nome for s in sup.servicos(env, tmp_path)] == ["worker"]


def test_so_quem_sobe_a_api_migra(tmp_path: Path) -> None:
    pg = {"REDIS_URL": "redis://r/0", "DATABASE_URL": "postgresql+asyncpg://u@db/x"}
    assert sup.precisa_migrar(pg, sup.servicos(pg, tmp_path)) is True
    so_worker = {**pg, "SHIELD_SERVICES": "worker"}
    assert sup.precisa_migrar(so_worker, sup.servicos(so_worker, tmp_path)) is False
    lite = {"REDIS_URL": "redis://r/0", "DATABASE_URL": "sqlite+aiosqlite:///x.db"}
    assert sup.precisa_migrar(lite, sup.servicos(lite, tmp_path)) is True
    lite_worker = {**lite, "SHIELD_SERVICES": "worker"}
    assert sup.precisa_migrar(lite_worker, sup.servicos(lite_worker, tmp_path)) is False


def test_sqlite_do_create_all_e_carimbado_antes_do_upgrade(tmp_path: Path) -> None:
    import sqlite3

    url = f"sqlite+aiosqlite:///{tmp_path / 'shield.db'}"
    assert sup.sqlite_sem_versao(url) is False  # não existe: upgrade cria tudo
    con = sqlite3.connect(tmp_path / "shield.db")
    con.execute("create table scans (id text)")
    con.commit()
    assert sup.sqlite_sem_versao(url) is True  # create_all sem alembic: carimba
    con.execute("create table alembic_version (version_num text)")
    con.commit()
    con.close()
    assert sup.sqlite_sem_versao(url) is False  # já versionado: só upgrade
    assert sup.sqlite_sem_versao("postgresql+asyncpg://u@db/x") is False


def test_scanner_nao_herda_segredo_da_api() -> None:
    env = {
        "APP_TOKEN": "a",
        "SESSION_SECRET": "s",
        "SETUP_CODE": "c",
        "SECRETS_KEY": "k",
        "REDIS_PASSWORD": "r",
        "REDIS_URL": "redis://:r@127.0.0.1:6379/0",
        "ZAP_API_KEY": "z",
        "DATABASE_URL": "postgresql://u:p@db/x",
        "PATH": "/bin",
    }
    worker = sup.ambiente_de("worker", env)
    assert not {"APP_TOKEN", "SESSION_SECRET", "SETUP_CODE", "REDIS_PASSWORD"} & set(worker)
    assert worker["SECRETS_KEY"] == "k" and worker["ZAP_API_KEY"] == "z"
    assert worker["REDIS_URL"] and worker["DATABASE_URL"]
    for nome in ("redis", "zap"):
        sobra = set(sup.ambiente_de(nome, env))
        assert sobra == {"PATH"}, (nome, sobra)
    assert sup.ambiente_de("orchestrator", env) == env


def test_redis_embutido_com_senha_por_arquivo(tmp_path: Path) -> None:
    env = sup.ambiente_base({"REDIS_PASSWORD": "segredo-redis", "PATH": ""}, tmp_path)
    assert env["REDIS_URL"] == "redis://:segredo-redis@127.0.0.1:6379/0"
    redis = next(s for s in sup.servicos(env, tmp_path) if s.nome == "redis")
    assert "segredo-redis" not in " ".join(redis.argv)
    conf = tmp_path / "secrets" / "redis.conf"
    assert conf.read_text() == "requirepass segredo-redis\n"
    assert oct(conf.stat().st_mode & 0o777) == "0o600"
    assert str(conf) in redis.argv
