"""Serviços, CPU e memória do container standalone, lidos do /proc e do cgroup.

A mesma forma de dado que o `roqueos-server` devolve em `/pentest/containers`
(`PentestContainerInfo`), para a tela portada desenhar os cartões sem saber que do
outro lado não há Docker. Cada "container" aqui é um processo do supervisor.

Fora do Linux (o Mac de quem desenvolve) não há /proc: a função devolve
`disponivel=False` e a tela diz que a leitura não existe, sem inventar número.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROC = Path("/proc")
CGROUP = Path("/sys/fs/cgroup")


@dataclass(frozen=True)
class Servico:
    nome: str  # o `service` que a tela usa
    rotulo: str
    assinatura: tuple[str, ...]  # pedaços do cmdline que identificam o processo


SERVICOS: tuple[Servico, ...] = (
    Servico("orchestrator", "API", ("uvicorn", "orchestrator.main:app")),
    Servico("worker", "Worker", ("arq", "orchestrator.jobs.queue.WorkerSettings")),
    Servico("redis", "Redis", ("redis-server",)),
    Servico("zap", "OWASP ZAP", ("zap", "-daemon")),
)


def _cmdlines(proc: Path) -> dict[int, list[str]]:
    saida: dict[int, list[str]] = {}
    for d in proc.iterdir():
        if not d.name.isdigit():
            continue
        try:
            partes = (d / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        saida[int(d.name)] = [p.decode("utf-8", "replace") for p in partes if p]
    return saida


def _casa(cmd: list[str], assinatura: tuple[str, ...]) -> bool:
    junto = " ".join(cmd)
    return all(a in junto for a in assinatura)


def _ticks(proc: Path, pid: int) -> int | None:
    try:
        campos = (proc / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        return int(campos[11]) + int(campos[12])  # utime + stime
    except (OSError, IndexError, ValueError):
        return None


def _rss(proc: Path, pid: int) -> int | None:
    try:
        for linha in (proc / str(pid) / "status").read_text().splitlines():
            if linha.startswith("VmRSS:"):
                return int(linha.split()[1]) * 1024
    except (OSError, ValueError):
        return None
    return None


def _inicio(proc: Path, pid: int) -> str | None:
    try:
        st = (proc / str(pid)).stat()
    except OSError:
        return None
    return datetime.fromtimestamp(st.st_mtime, UTC).isoformat()


def _memoria_da_maquina(proc: Path = PROC) -> int | None:
    try:
        for linha in (proc / "meminfo").read_text().splitlines():
            if linha.startswith("MemTotal:"):
                return int(linha.split()[1]) * 1024
    except (OSError, ValueError):
        return None
    return None


def _limite_de_memoria(cgroup: Path, proc: Path = PROC) -> int | None:
    """O teto do container; sem teto (`max`, o padrão do `docker run`), a memória da máquina."""
    try:
        bruto = (cgroup / "memory.max").read_text().strip()
    except OSError:
        return None
    return _memoria_da_maquina(proc) if bruto == "max" else int(bruto)


def servicos(proc: Path = PROC, cgroup: Path = CGROUP, janela: float = 0.25) -> dict[str, Any]:
    """Um cartão por serviço conhecido. Processo que não está rodando vem `exited`."""
    agora = datetime.now(UTC).isoformat()
    if not proc.exists():
        return {"containers": [], "at": agora, "disponivel": False}
    cmds = _cmdlines(proc)
    hz = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
    limite = _limite_de_memoria(cgroup)
    achados: dict[str, int | None] = {}
    for s in SERVICOS:
        achados[s.nome] = next((pid for pid, c in cmds.items() if _casa(c, s.assinatura)), None)
    t0 = {n: _ticks(proc, p) for n, p in achados.items() if p}
    time.sleep(janela)
    t1 = {n: _ticks(proc, p) for n, p in achados.items() if p}
    cartoes = []
    for s in SERVICOS:
        pid = achados[s.nome]
        cpu = None
        if pid and t0.get(s.nome) is not None and t1.get(s.nome) is not None:
            cpu = round(((t1[s.nome] - t0[s.nome]) / hz) / janela * 100, 1)  # type: ignore[operator]
        cartoes.append(
            {
                "service": s.nome,
                "name": s.rotulo,
                "image": "roqueos-shield",
                "state": "running" if pid else "exited",
                "status": f"pid {pid}" if pid else "parado",
                "health": None,
                "startedAt": _inicio(proc, pid) if pid else None,
                "restartCount": 0,
                "cpuPercent": cpu,
                "memUsage": _rss(proc, pid) if pid else None,
                "memLimit": limite,
            }
        )
    return {"containers": cartoes, "at": agora, "disponivel": True}


def uso_do_container(cgroup: Path = CGROUP, janela: float = 0.25) -> dict[str, Any]:
    """CPU e memória do container inteiro (cgroup v2). `disponivel=False` sem cgroup."""
    try:

        def uso_cpu() -> int:
            for linha in (cgroup / "cpu.stat").read_text().splitlines():
                if linha.startswith("usage_usec"):
                    return int(linha.split()[1])
            raise ValueError("cpu.stat sem usage_usec")

        a = uso_cpu()
        time.sleep(janela)
        b = uso_cpu()
        mem = int((cgroup / "memory.current").read_text().strip())
    except (OSError, ValueError):
        return {"disponivel": False}
    ncpu = os.cpu_count() or 1
    limite = _limite_de_memoria(cgroup)
    return {
        "disponivel": True,
        "cpuPercent": round((b - a) / (janela * 1_000_000) / ncpu * 100, 1),
        "memUsage": mem,
        "memLimit": limite,
        "memPercent": round(mem / limite * 100, 1) if limite else None,
    }
