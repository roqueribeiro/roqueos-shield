"""O supervisor do container standalone: um processo que sobe e vigia os outros.

`docker run roqueos-shield-standalone` cai aqui. Ele:

1. garante os segredos do primeiro boot (`segredos.garantir`) e os põe no ambiente
   dos filhos, sem imprimir nenhum;
2. sobe, nesta ordem, o Redis (só em 127.0.0.1), o ZAP (se a imagem tiver), a API e
   o worker;
3. leva a saída de cada um para o stdout do container e para o Redis (`logtee`), que
   é de onde a aba Execução da tela lê;
4. reinicia quem cair, com espera crescente, e conta os reinícios;
5. no SIGTERM do `docker stop`, para todos em ordem inversa e sai.

Python e não s6-overlay: roda como o usuário 1000 da imagem (s6 quer root no PID 1),
não traz binário de fora, e é testável aqui mesmo (`test_standalone_supervisor.py`).

Variável que já vem no ambiente vence: quem aponta `REDIS_URL` para um Redis de fora
não ganha o Redis embutido; `ZAP_BASE_URL` de fora desliga o ZAP embutido; e assim por
diante. É o mesmo container servindo o `docker run` de quem só quer usar e o
`compose.prod.yml` de quem separa os serviços.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.standalone import segredos
from orchestrator.standalone.logtee import Tee

REDIS_LOCAL = "redis://127.0.0.1:6379/0"

# O que cada processo NÃO recebe do ambiente. Os scanners rodam como filhos do worker,
# herdam o ambiente dele e processam conteúdo do alvo: lá não entra o APP_TOKEN (admin
# de serviço), nem a chave que assina sessão, nem o código de primeiro uso. O worker
# fica com a SECRETS_KEY porque decifra a chave de IA guardada. Redis e ZAP recebem o
# que precisam pela linha de comando ou arquivo, e mais nada.
_SO_DA_API = frozenset({"APP_TOKEN", "SESSION_SECRET", "SETUP_CODE"})
_SEGREDOS = frozenset(segredos.SEGREDOS) | {"DATABASE_URL", "REDIS_URL"}
_FORA_DE: dict[str, frozenset[str]] = {
    "orchestrator": frozenset(),
    "worker": _SO_DA_API | {"REDIS_PASSWORD"},
    "redis": _SEGREDOS,
    "zap": _SEGREDOS,
}


def ambiente_de(nome: str, env: dict[str, str]) -> dict[str, str]:
    fora = _FORA_DE.get(nome, _SEGREDOS)
    return {k: v for k, v in env.items() if k not in fora}


def _redis_embutido(url: str) -> bool:
    """O REDIS_URL aponta para o Redis deste container (com ou sem senha)?"""
    from urllib.parse import urlparse

    u = urlparse(url)
    return u.scheme == "redis" and u.hostname == "127.0.0.1" and (u.port or 6379) == 6379


ZAP_LOCAL = "http://127.0.0.1:8090"
ESPERA_MAX = 60.0


@dataclass
class Servico:
    nome: str
    argv: list[str]
    ativo: bool = True
    reinicios: int = 0
    processo: Any = None
    env: dict[str, str] = field(default_factory=dict)


def ambiente_base(env: dict[str, str], data: Path) -> dict[str, str]:
    """O ambiente dos filhos: o do container, mais o que o standalone completa."""
    saida = dict(env)
    saida.setdefault("DATA_DIR", str(data))
    saida.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{data / 'shield.db'}")
    saida.setdefault("REPORTS_DIR", str(data / "reports"))
    if "REDIS_URL" not in saida:
        senha = saida.get("REDIS_PASSWORD", "")
        saida["REDIS_URL"] = f"redis://:{senha}@127.0.0.1:6379/0" if senha else REDIS_LOCAL
    saida.setdefault("TRIVY_SERVER_URL", "")  # trivy em modo cliente, cache local
    saida.setdefault("TRIVY_CACHE_DIR", str(data / "trivy-cache"))
    saida.setdefault("LOG_FORMAT", "json")
    if shutil.which("zap.sh", path=saida.get("PATH")):
        saida.setdefault("ZAP_BASE_URL", ZAP_LOCAL)
    return saida


def servicos(env: dict[str, str], data: Path) -> list[Servico]:
    """A lista do que sobe, já decidida pelo ambiente.

    `SHIELD_SERVICES` (ex.: `orchestrator` ou `worker`) restringe a lista: é como o
    `compose.prod.yml` roda a API e N workers em containers separados com a mesma imagem.
    """
    py = sys.executable
    lista: list[Servico] = []
    if _redis_embutido(env.get("REDIS_URL", "")):
        # Senha por arquivo de config (0600), não por argumento: argumento aparece no
        # /proc/<pid>/cmdline de qualquer processo do container.
        conf: list[str] = []
        if env.get("REDIS_PASSWORD"):
            arq = data / "secrets" / "redis.conf"
            arq.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(arq, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"requirepass {env['REDIS_PASSWORD']}\n")
            conf = [str(arq)]
        lista.append(
            Servico(
                "redis",
                [
                    "redis-server",
                    *conf,
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    "6379",
                    "--protected-mode",
                    "yes",
                    "--save",
                    "",
                    "--appendonly",
                    "no",
                    "--dir",
                    str(data),
                ],
            )
        )
    if env.get("ZAP_BASE_URL") == ZAP_LOCAL:
        lista.append(
            Servico(
                "zap",
                [
                    "zap.sh",
                    "-daemon",
                    "-host",
                    "127.0.0.1",
                    "-port",
                    "8090",
                    "-dir",
                    str(data / "zap"),
                    "-config",
                    "api.disablekey=false",
                    "-config",
                    f"api.key={env.get('ZAP_API_KEY', '')}",
                ],
            )
        )
    porta = env.get("PORT", "8080")
    lista.append(
        Servico(
            "orchestrator",
            [
                py,
                "-m",
                "uvicorn",
                "orchestrator.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                porta,
                "--proxy-headers",
                # Sem log de acesso: a aba Execução lê os logs por polling, e cada leitura
                # virava uma linha nova no próprio log que ela mostrava.
                "--no-access-log",
            ],
        )
    )
    lista.append(Servico("worker", [py, "-m", "arq", "orchestrator.jobs.queue.WorkerSettings"]))
    so = {x.strip() for x in env.get("SHIELD_SERVICES", "").split(",") if x.strip()}
    return [svc for svc in lista if not so or svc.nome in so]


# A primeira versão com o standalone (0.5.0) nasce no schema 0008. Um SQLite criado
# pelo `create_all` dessa versão, sem `alembic_version`, está nesse ponto.
BASE_DO_STANDALONE = "0008"


def precisa_migrar(env: dict[str, str], lista: list[Servico]) -> bool:
    """Com a API neste container, o alembic roda antes de servir, em Postgres e SQLite.

    Em Postgres o schema (e o trigger que torna a trilha de auditoria imutável) vem das
    migrations. Em SQLite também: o `create_all` do boot cria tabela nova mas não põe
    coluna nova numa tabela que já existe, então o volume de uma versão antiga ficaria
    sem a coluna depois do upgrade da imagem. Só quem sobe a API migra, para N workers
    não disputarem a migração.
    """
    url = env.get("DATABASE_URL", "")
    return url.startswith(("postgresql", "sqlite")) and any(s.nome == "orchestrator" for s in lista)


def sqlite_sem_versao(url: str) -> bool:
    """SQLite com tabelas e sem `alembic_version`: criado pelo `create_all`.

    O alembic tentaria criar de novo o que já existe. Esse banco é carimbado na base do
    standalone antes do upgrade. Banco que não existe ou está vazio segue o upgrade
    normal, que cria tudo.
    """
    if not url.startswith("sqlite"):
        return False
    caminho = Path(url.split(":///", 1)[-1])
    if not caminho.is_file():
        return False
    import sqlite3

    con = sqlite3.connect(caminho)
    try:
        tabelas = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    finally:
        con.close()
    return bool(tabelas) and "alembic_version" not in tabelas


def espera(reinicios: int) -> float:
    """1s, 2s, 4s… até 60s. Processo que cai em laço não vira laço de CPU."""
    return float(min(ESPERA_MAX, 2 ** max(0, reinicios - 1)))


async def _bombear(svc: Servico, fluxo: asyncio.StreamReader, tee: Tee) -> None:
    while True:
        linha = await fluxo.readline()
        if not linha:
            return
        tee.linha(linha.decode("utf-8", "replace"))


async def _rodar(svc: Servico, redis_cliente: Any, parar: asyncio.Event) -> None:
    tee = Tee(svc.nome, redis_cliente, sys.stdout)
    while not parar.is_set():
        try:
            svc.processo = await asyncio.create_subprocess_exec(
                *svc.argv,
                env=svc.env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as e:
            tee.linha(f"[supervisor] {svc.nome} não iniciou: {type(e).__name__}: {e}\n")
            svc.processo = None
        else:
            assert svc.processo.stdout is not None
            await _bombear(svc, svc.processo.stdout, tee)
            codigo = await svc.processo.wait()
            if parar.is_set():
                return
            tee.linha(f"[supervisor] {svc.nome} saiu com código {codigo}\n")
        svc.reinicios += 1
        try:
            await asyncio.wait_for(parar.wait(), timeout=espera(svc.reinicios))
        except TimeoutError:
            continue


async def _encerrar(lista: list[Servico], prazo: float = 8.0) -> None:
    """Para em ordem inversa (API antes do Redis), com `prazo` segundos NO TOTAL.

    O `docker stop` manda SIGKILL em 10 s por padrão. Com prazo por processo, quatro
    serviços lentos somavam mais que isso e o último morria sem SIGTERM. Quem não sai a
    tempo leva SIGKILL daqui, ainda dentro da janela do Docker.
    """
    loop = asyncio.get_running_loop()
    fim = loop.time() + prazo
    for svc in reversed(lista):
        p = svc.processo
        if p is None or p.returncode is not None:
            continue
        p.terminate()
        try:
            await asyncio.wait_for(p.wait(), timeout=max(0.1, fim - loop.time()))
        except TimeoutError:
            p.kill()


async def principal(env: dict[str, str] | None = None) -> int:
    base = dict(os.environ if env is None else env)
    data = Path(base.get("DATA_DIR", "/data"))
    data.mkdir(parents=True, exist_ok=True)
    valores, origens = segredos.garantir(data / "secrets", ambiente=base)
    for o in origens:
        print(f"[supervisor] segredo {o.nome}: {o.de_onde}", flush=True)
    filho = ambiente_base({**base, **valores}, data)
    lista = servicos(filho, data)
    for svc in lista:
        svc.env = ambiente_de(svc.nome, filho)
    if any(o.nome == "SETUP_CODE" and o.de_onde != "ambiente" for o in origens):
        print(
            "[supervisor] se o primeiro uso ainda não foi feito, o código para criar o admin está em "
            f"{data / 'secrets' / 'SETUP_CODE'} "
            "(docker exec <container> cat /data/secrets/SETUP_CODE)",
            flush=True,
        )
    print("[supervisor] serviços: " + ", ".join(s.nome for s in lista), flush=True)
    if precisa_migrar(filho, lista):
        passos = [["upgrade", "head"]]
        if sqlite_sem_versao(filho["DATABASE_URL"]):
            passos.insert(0, ["stamp", BASE_DO_STANDALONE])
        for passo in passos:
            print("[supervisor] alembic " + " ".join(passo), flush=True)
            mig = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "alembic", *passo, env=filho
            )
            if await mig.wait() != 0:
                print("[supervisor] a migração falhou; a API não sobe sem o schema", flush=True)
                return 1

    redis_cliente: Any = None
    try:
        from redis import Redis

        redis_cliente = Redis.from_url(
            filho["REDIS_URL"], socket_connect_timeout=1, socket_timeout=1
        )
    except Exception:  # noqa: BLE001
        redis_cliente = None

    parar = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sinal in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sinal, parar.set)
    tarefas = [asyncio.create_task(_rodar(svc, redis_cliente, parar)) for svc in lista]
    await parar.wait()
    print("[supervisor] parando", flush=True)
    await _encerrar(lista)
    for t in tarefas:
        t.cancel()
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(principal()))


if __name__ == "__main__":
    main()
