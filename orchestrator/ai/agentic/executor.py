"""A coleira do agente ofensivo — onde a trava é MECANISMO, não prosa.

Antes disto, o escopo do agente existia só como frase no system prompt ("respeite o
escopo do contrato"), e a única função que executava algo (`kali_run_readonly`) era
código morto com allowlist de 8 binários read-only. Prompt não contém um agente com
shell: a trava tem que estar no executor.

O que este módulo garante, em ordem, ANTES de qualquer comando rodar:

1. **Fase**  — cada comando pertence a uma fase (recon / exploração dirigida). O que
   não está na allowlist da fase não roda. Nada de brute force, fuzzing pesado ou
   qualquer coisa que derrube serviço.
2. **Escopo** — o alvo passa pelo mesmo `target_validator` dos scanners (allowlist,
   LAB_ONLY, bloqueio de rede privada/IMDS, anti-argv-injection). Alvo fora do
   escrito não roda, e a recusa é registrada.
3. **Argumentos** — nada de shell (`argv` list, nunca `shell=True`), nada de
   metacaractere, nada de flag que escreva em disco ou saia do alvo.
4. **dry_run** — quando ligado (default), o comando é PLANEJADO e devolvido, nunca
   executado. Antes, `dry_run` era um bool que não ramificava em lugar nenhum.
5. **Timeout e saída limitada** — comando pendurado não trava o loop.

Toda decisão (executado, recusado, por quê) volta no resultado, para o chamador
gravar no `audit_log`.
"""

from __future__ import annotations

import asyncio
import re
import shlex
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

from orchestrator.config import settings
from orchestrator.domain.target_validator import (
    TargetValidationError,
    validate_target_value,
)

log = structlog.get_logger(__name__)


class Phase(StrEnum):
    """Fase da investigação. A fase decide o que pode rodar."""

    RECON = "recon"
    EXPLOIT = "exploit"


# Allowlist POR FASE. Só binário que descobre/valida, nunca que derruba.
# Fora desta tabela = recusado, mesmo que o modelo insista.
_ALLOWED: dict[Phase, frozenset[str]] = {
    Phase.RECON: frozenset(
        {
            "nmap",
            "naabu",
            "httpx",
            "subfinder",
            "dig",
            "host",
            "nslookup",
            "whois",
            "curl",
            "openssl",
        }
    ),
    # Exploração DIRIGIDA: valida um finding específico. sqlmap/nuclei entram aqui
    # com limites duros abaixo; nada de brute force (hydra, medusa, patator) e nada
    # de fuzzing pesado (ffuf/gobuster ficam de fora de propósito).
    Phase.EXPLOIT: frozenset({"sqlmap", "nuclei", "nikto", "curl", "openssl"}),
}

# Binários explicitamente proibidos em qualquer fase — a lista existe para que a
# recusa seja NOMEADA no audit, em vez de cair no genérico "não está na allowlist".
_NEVER: frozenset[str] = frozenset(
    {
        "hydra",
        "medusa",
        "patator",
        "ncrack",  # brute force
        "msfconsole",
        "msfvenom",  # exploração não dirigida
        "ffuf",
        "gobuster",
        "dirsearch",
        "wfuzz",  # fuzzing pesado
        "slowhttptest",
        "hping3",
        "t50",  # DoS
        "rm",
        "dd",
        "mkfs",
        "shutdown",
        "reboot",
        "kill",  # destrutivo
        "bash",
        "sh",
        "zsh",
        "python",
        "python3",
        "perl",
        "ruby",
        "nc",
        "ncat",  # shell/reverse
    }
)

# Flags recusadas: escrevem em disco, leem arquivo local, ou dão shell.
# Casadas por PREFIXO (regex), não igualdade: `-oN`/`-oX`/`-oA` do nmap e
# `--os-shell` do sqlmap passariam por uma lista de igualdade — este furo foi achado
# pelo próprio teste da coleira antes do agente existir.
_BANNED_ARG_RE = re.compile(
    r"""^(
        -o            # -o, -oN, -oX, -oG, -oA (nmap), -o arquivo (curl)
      | --output
      | --os-         # --os-shell, --os-pwn, --os-cmd (sqlmap)
      | --sql-shell
      | --eval
      | -e$
      | -w$ | --wordlist
      | -iL | --file
      | --script-args
      | --upload | --interactive
      | --data-binary=@
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# Metacaracteres de shell: mesmo com argv list, um argumento com isto é sinal de
# tentativa de injeção (vinda do modelo ou de texto de um alvo malicioso).
_SHELL_METACHARS: frozenset[str] = frozenset({";", "|", "&", "$", "`", ">", "<", "\n", "\r"})

# Limites duros por fase (o agente não escolhe).
_MAX_OUTPUT = 8000
DEFAULT_TIMEOUT = 60.0
MAX_TIMEOUT = 180.0


@dataclass
class ExecDecision:
    """O que o executor decidiu, e por quê. Vai inteiro pro audit_log."""

    allowed: bool
    executed: bool
    reason: str
    command: list[str] = field(default_factory=list)
    phase: str = ""
    target: str | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""

    def to_audit(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "executed": self.executed,
            "reason": self.reason,
            "command": " ".join(self.command),
            "phase": self.phase,
            "target": self.target,
            "exit_code": self.exit_code,
        }


def _binary_of(command: list[str]) -> str:
    return (command[0] if command else "").strip().lower()


def check_command(
    command: list[str], *, phase: Phase, target: str | None, asset_type: str | None = None
) -> ExecDecision:
    """Decide se o comando PODE rodar. Puro: sem I/O, testável, e é o gate real.

    Devolve sempre uma `ExecDecision`; `allowed=False` traz o motivo nomeado.
    """
    binary = _binary_of(command)
    d = lambda ok, why: ExecDecision(  # noqa: E731
        allowed=ok,
        executed=False,
        reason=why,
        command=list(command),
        phase=phase.value,
        target=target,
    )

    if not command or not binary:
        return d(False, "comando vazio")

    if binary in _NEVER:
        return d(False, f"binário '{binary}' é proibido em qualquer fase (brute force/DoS/shell)")

    allowed_for_phase = _ALLOWED.get(phase, frozenset())
    if binary not in allowed_for_phase:
        return d(
            False,
            f"binário '{binary}' não está na allowlist da fase '{phase.value}' "
            f"({', '.join(sorted(allowed_for_phase))})",
        )

    for arg in command[1:]:
        if any(ch in arg for ch in _SHELL_METACHARS):
            return d(False, f"argumento com metacaractere de shell: {arg!r}")
        if _BANNED_ARG_RE.match(arg):
            return d(False, f"flag '{arg}' recusada (escrita em disco/leitura local/shell)")

    # Escopo: o alvo passa pelo MESMO validador dos scanners.
    if target:
        try:
            validate_target_value(target, asset_type=asset_type)
        except TargetValidationError as e:
            return d(False, f"alvo fora do escopo autorizado: {e}")

    return ExecDecision(
        allowed=True,
        executed=False,
        reason="autorizado",
        command=list(command),
        phase=phase.value,
        target=target,
    )


async def run_in_kali(
    command: list[str],
    *,
    phase: Phase,
    target: str | None,
    asset_type: str | None = None,
    dry_run: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
    container: str = "cai-kali-toolbox",
    runner: Any = None,
) -> ExecDecision:
    """Roda um comando no kali-toolbox — se, e só se, a coleira deixar.

    `dry_run=True` (default) PLANEJA e não executa: é o que torna o parâmetro real,
    e não um bool decorativo como era antes. `runner` permite injetar o executor nos
    testes (sem docker) sem afrouxar nenhuma checagem.
    """
    decision = check_command(command, phase=phase, target=target, asset_type=asset_type)
    if not decision.allowed:
        log.warning(
            "agent.command_refused",
            reason=decision.reason,
            binary=_binary_of(command),
            phase=phase.value,
        )
        return decision

    if dry_run:
        decision.reason = "dry_run: comando planejado, não executado"
        log.info("agent.command_planned", command=" ".join(command), phase=phase.value)
        return decision

    exec_timeout = min(max(timeout, 1.0), MAX_TIMEOUT)
    argv = ["docker", "exec", container, *command]
    _run = runner or _docker_exec
    try:
        rc, out, err = await asyncio.wait_for(_run(argv), timeout=exec_timeout)
    except TimeoutError:
        decision.reason = f"timeout após {exec_timeout}s"
        return decision
    except Exception as e:  # noqa: BLE001
        decision.reason = f"falha ao executar: {e}"
        return decision

    decision.executed = True
    decision.reason = "executado"
    decision.exit_code = rc
    decision.stdout = out[:_MAX_OUTPUT]
    decision.stderr = err[:2000]
    log.info("agent.command_executed", command=" ".join(command), exit_code=rc)
    return decision


async def _docker_exec(argv: list[str]) -> tuple[int, str, str]:
    """Executor real: `docker exec` com argv list — nunca shell."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def parse_command(raw: str | list[str]) -> list[str]:
    """Converte o comando que o modelo propôs em argv list, sem passar por shell."""
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return shlex.split(raw)


def lab_only_active() -> bool:
    """True quando o agente está preso ao lab (LAB_ONLY + allowlist)."""
    return bool(settings.LAB_ONLY)
