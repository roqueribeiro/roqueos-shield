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
import os
import re
import shlex
import shutil
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

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
      | --script          # --script e --script-args: NSE é Lua com os.execute
      | --upload | --interactive
      | --data-binary=@
      | --config          # curl lê opções (e URLs) de arquivo (-K: por binário)
      | --resolve | --connect-to | --proxy | --socks  # desviam a conexão (-x: por binário)
      | -L$ | --location # redirect segue para onde o alvo mandar
      | --unix-socket | --abstract-unix-socket
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# O curl tem mais de 250 opções, e dezenas leem ou escrevem arquivo (-T, -K, -b, -c,
# -D, -E, --cert, --key, -w @arq, --data-urlencode x@arq...), aceitando o valor colado
# (`-T/data/x`) e em grupo (`-sd@/data/x`). Lista negra não fecha isso (revisão do PR
# #20, duas rodadas), então o curl tem LISTA DO QUE PODE. Fora dela, recusado.
_CURL_SEM_VALOR = frozenset("sSIikvfgNq46G")  # agrupáveis: -sSIk
_CURL_COM_VALOR = frozenset("XHAemd")  # o valor vem no próximo argumento ou colado
_CURL_LONGAS = frozenset(
    {
        "--silent",
        "--show-error",
        "--head",
        "--include",
        "--insecure",
        "--verbose",
        "--fail",
        "--globoff",
        "--no-buffer",
        "--get",
        "--compressed",
        "--path-as-is",
        "--http1.1",
        "--http2",
        "--request",
        "--header",
        "--user-agent",
        "--referer",
        "--max-time",
        "--connect-timeout",
        "--data",
        "--data-raw",
    }
)


def _curl_fora_da_lista(arg: str) -> str | None:
    """Motivo para recusar uma opção do curl que não está na lista do que pode."""
    if arg.startswith("--"):
        nome = arg.split("=", 1)[0]
        return None if nome in _CURL_LONGAS else f"opção {nome} do curl fora da lista permitida"
    if not arg.startswith("-") or arg == "-":
        return None
    letras = arg[1:]
    for c in letras:
        if c in _CURL_SEM_VALOR:
            continue
        if c in _CURL_COM_VALOR:
            return None  # o resto do token é o valor, conferido como argumento
        return f"opção -{c} do curl fora da lista permitida"
    return None


# Esquemas que um argumento pode trazer. Qualquer outro (`file:`, `gopher:`, `dict:`,
# `ftp:`, `ldap:`) lê disco ou fala protocolo interno.
_ESQUEMAS_OK = frozenset({"http", "https"})

# Nome com ponto e TLD alfabético, ou localhost. IP literal é conferido à parte (com o
# ipaddress): um regex de dígitos e pontos confundia o `4` do `-T4` com um host.
_PARECE_HOST = re.compile(
    r"^(localhost|[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z][a-z0-9-]*)(:[0-9]+)?$",
    re.IGNORECASE,
)


def _e_ip(texto: str) -> bool:
    import ipaddress

    t = texto.strip("[]")
    if t.count(":") == 1 and "." in t:  # 1.2.3.4:80
        t = t.split(":", 1)[0]
    elif t.startswith("[") is False and "]:" in texto:
        t = texto[1 : texto.index("]")]
    try:
        ipaddress.ip_address(t)
        return True
    except ValueError:
        return False


def _host_do_alvo(target: str) -> str:
    """O host de um alvo (URL, host:porta, domínio, host/caminho)."""
    t = target.strip()
    if "://" in t:
        return (urlparse(t).hostname or "").lower()
    t = t.split("/", 1)[0]
    if t.startswith("["):
        return t[1 : t.find("]")].lower() if "]" in t else t.lower()
    if t.count(":") == 1:
        t = t.split(":", 1)[0]
    return t.lower()


def _argumento_fora_do_alvo(arg: str, host_alvo: str) -> str | None:
    """Motivo para recusar um argumento que leva a outro lugar que não o alvo.

    A coleira validava o alvo do finding e deixava o argv livre: `curl
    file:///data/secrets/APP_TOKEN`, `curl -d @arquivo`, `nmap 169.254.169.254` e
    `curl http://127.0.0.1:8080/` passavam com o alvo do finding em ordem (revisão de
    segurança de 07/11/2026). Agora todo URL, host, IP, caminho ou arquivo no argv
    tem que ser o próprio alvo, ou não roda.
    """
    if arg.startswith("-"):
        # O valor de uma opção vem depois do `=` (`--data=@x`) ou colado na curta
        # (`-d@x`, `-T/caminho`). Opção longa sem `=` não leva valor no mesmo token,
        # mas `@` e `://` nela também não têm uso legítimo.
        if "=" in arg:
            arg = arg.split("=", 1)[1]
        elif not arg.startswith("--") and len(arg) > 2:
            # Valor colado na curta (`-T/caminho`, `-t/var/x.yaml`). Em grupo (`-sd@x`)
            # o curl é barrado pela lista do que pode; os outros binários não agrupam.
            arg = arg[2:]
        else:
            return "lê arquivo local (@arquivo)" if "@" in arg or "://" in arg else None
    if not arg:
        return None
    if arg.startswith("@") or "=@" in arg or ",@" in arg or ";@" in arg:
        return "lê arquivo local (@arquivo)"
    if arg.startswith(("/", "./", "../", "~")) or "/../" in arg:
        return "caminho de arquivo local"
    if "://" in arg:
        p = urlparse(arg)
        if p.scheme.lower() not in _ESQUEMAS_OK:
            return f"esquema '{p.scheme}' não permitido"
        if (p.hostname or "").lower() != host_alvo:
            return f"URL para outro host ({p.hostname!r}), não o alvo"
        return None
    if ":" in arg and arg.split(":", 1)[0].lower() in {"file", "gopher", "dict", "ftp", "ldap"}:
        return "esquema não permitido"
    base, _, resto = arg.partition("/")
    # Endereço numérico em forma que o ipaddress não aceita mas o nmap e o curl aceitam:
    # `127.1`, `2130706433`, `0x7f000001`, `[::1]:8080`. Porta (`80`, `1-1000`,
    # `80,443`) e o `4` do `-T4` não têm ponto, dois-pontos nem 6+ dígitos.
    numerico = re.fullmatch(r"[0-9a-fA-FxX.:\[\]]+", base) is not None and (
        any(c in base for c in ".:[") or base.lower().startswith("0x") or len(base) >= 6
    )
    if numerico and _host_do_alvo(base) != host_alvo:
        return f"endereço numérico {base!r} não é o alvo"
    if _PARECE_HOST.match(base) or _e_ip(base):
        h = _host_do_alvo(base)
        if h != host_alvo:
            return f"host {h!r} não é o alvo"
        if resto[:1].isdigit():
            return "faixa de rede (CIDR) no lugar do alvo"
    return None


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

    if not target:
        return d(False, "sem alvo: o agente só roda comando contra o alvo do finding")
    host_alvo = _host_do_alvo(target)
    for arg in command[1:]:
        if any(ch in arg for ch in _SHELL_METACHARS):
            return d(False, f"argumento com metacaractere de shell: {arg!r}")
        if binary == "curl":
            if motivo := _curl_fora_da_lista(arg):
                return d(False, f"argumento {arg!r} recusado: {motivo}")
            if "@" in arg and "://" not in arg:
                # `-d @arq`, `--data-urlencode x@arq`, `-F f=@arq`: o curl lê o arquivo.
                return d(False, f"argumento {arg!r} recusado: lê arquivo local (@)")
        elif _BANNED_ARG_RE.match(arg):
            return d(False, f"flag '{arg}' recusada (escrita em disco/leitura local/shell)")
        motivo = _argumento_fora_do_alvo(arg, host_alvo)
        if motivo:
            return d(False, f"argumento {arg!r} recusado: {motivo}")

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


_AMBIENTE_DO_COMANDO = frozenset({"PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR"})


async def _local_exec(argv: list[str]) -> tuple[int, str, str]:
    """Executor local: o binário roda no próprio container do orchestrator.

    É o mesmo modelo que os scanners já usam em produção — o Dockerfile do
    orchestrator embute nmap/nuclei/gitleaks e diz, textualmente, "no kali-toolbox
    sidecar for the core scan set". Sem este modo, o agente não rodaria no stack que
    o RoqueShield publica, porque lá o container Kali não sobe. A coleira é a MESMA
    nos dois modos: o que muda é onde o processo nasce, não o que ele pode ser.
    """
    # Ambiente mínimo: o processo da API tem APP_TOKEN, SESSION_SECRET e a chave de
    # cifra no ambiente, e nada disso é da conta de um nmap ou de um curl.
    env = {k: v for k, v in os.environ.items() if k in _AMBIENTE_DO_COMANDO}
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


async def _kali_available(container: str) -> bool:
    """O container Kali está de pé e alcançável?"""
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            docker,
            "inspect",
            "-f",
            "{{.State.Running}}",
            container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return proc.returncode == 0 and out.decode().strip() == "true"
    except (OSError, TimeoutError):
        return False


async def resolve_executor(container: str = "cai-kali-toolbox") -> str:
    """Decide onde o comando roda: `kali` (isolado) ou `local` (in-process).

    `AGENT_EXECUTOR=auto` (default) prefere o Kali quando ele existe — mais
    isolamento — e cai para local quando não existe, que é o caso do stack padrão do
    RoqueShield. `kali` e `local` forçam um dos dois.
    """
    mode = (settings.AGENT_EXECUTOR or "auto").strip().lower()
    if mode in {"kali", "local"}:
        return mode
    return "kali" if await _kali_available(container) else "local"


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
    mode: str | None = None,
) -> ExecDecision:
    """Roda um comando de segurança — se, e só se, a coleira deixar.

    `dry_run=True` (default) PLANEJA e não executa: é o que torna o parâmetro real,
    e não um bool decorativo como era antes. `runner` permite injetar o executor nos
    testes sem afrouxar nenhuma checagem. `mode` força kali/local (default: resolve).
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
    effective_mode = mode or await resolve_executor(container)
    if effective_mode == "kali":
        argv = ["docker", "exec", container, *command]
        _run = runner or _docker_exec
    else:
        argv = list(command)
        _run = runner or _local_exec
    decision.reason = f"executando ({effective_mode})"
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
