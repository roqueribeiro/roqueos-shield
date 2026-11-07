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
    saida.setdefault("REDIS_URL", REDIS_LOCAL)
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
    if env.get("REDIS_URL") == REDIS_LOCAL:
        lista.append(
            Servico(
                "redis",
                [
                    "redis-server",
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


def precisa_migrar(env: dict[str, str], lista: list[Servico]) -> bool:
    """Postgres com a API neste container: roda o alembic antes de servir.

    Em SQLite a API cria as tabelas no boot; em Postgres o schema (e o trigger que torna
    a trilha de auditoria imutável) vem das migrations, e servir sem elas é servir sem a
    garantia. Só quem sobe a API migra, para N workers não disputarem a migração.
    """
    return env.get("DATABASE_URL", "").startswith("postgresql") and any(
        s.nome == "orchestrator" for s in lista
    )


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


async def _encerrar(lista: list[Servico], prazo: float = 20.0) -> None:
    for svc in reversed(lista):
        p = svc.processo
        if p is None or p.returncode is not None:
            continue
        p.terminate()
        try:
            await asyncio.wait_for(p.wait(), timeout=prazo)
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
        svc.env = filho
    print("[supervisor] serviços: " + ", ".join(s.nome for s in lista), flush=True)
    if precisa_migrar(filho, lista):
        print("[supervisor] alembic upgrade head", flush=True)
        mig = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "alembic", "upgrade", "head", env=filho
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
