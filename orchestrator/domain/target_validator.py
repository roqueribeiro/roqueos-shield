"""Validador de target.value — bloqueia injeção de flags (H4) e SSRF (H5).

Aplicado ANTES de qualquer enqueue de scan ou criação de target. Rejeita:

- Strings que começam com `-`/`--` (argv injection nos adapters subprocess).
- Hosts em ranges privados/loopback/link-local quando `LAB_ONLY=true` E o host
  não está em `TARGET_ALLOWLIST`. Bloqueia metadata IMDS (169.254.169.254),
  serviços internos da rede `cai-net` (postgres, redis), e RFC1918.
- Schemes não-HTTP/HTTPS em URLs (rejeita `file://`, `gopher://`, etc.).

Quando `LAB_ONLY=true` E `TARGET_ALLOWLIST` contém o host/IP/CIDR, permite
(é o caminho intencional pra Juice Shop/DVWA/WebGoat no lab).

Conformidade: este é o coração do compliance gate. Mexer aqui requer review.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from orchestrator.config import settings


class TargetValidationError(ValueError):
    """Levantada quando target.value é rejeitado por policy."""


# Domínios/IPs que NÃO podem ser alvo quando LAB_ONLY=true sem allowlist explícita.
# RFC1918, loopback, link-local, IMDS, ULA IPv6.
_FORBIDDEN_HOSTNAMES: frozenset[str] = frozenset(
    {"localhost", "metadata.google.internal", "metadata", "instance-data"}
)

_HOSTNAME_RE = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
)


def _ip_is_blocked(ip_str: str) -> bool:
    """True se o IP cai em range privado/loopback/link-local/reservado."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_host_ips(host: str) -> list[str]:
    """Resolve um hostname para a lista de IPs (v4+v6). Vazio se não resolver.

    Isolado numa função própria de propósito, para o teste fazer monkeypatch sem
    depender de DNS real.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return []
    return [str(info[4][0]) for info in infos]


def _is_blocked_network(host: str) -> bool:
    """True se o host é sentinela, IP-literal bloqueado, OU resolve para um IP bloqueado.

    SEC-04: a versão anterior só checava IP-literal — então um hostname como
    `postgres`, `redis` ou `metadata.attacker.com` passava direto (o `ip_address`
    levantava ValueError e a função retornava False), abrindo SSRF por nome contra
    os serviços da `cai-net` e o IMDS. Agora hostnames são resolvidos e bloqueados
    se QUALQUER IP resolvido cair em rede interna. Nota: isto fecha o SSRF por nome;
    a defesa completa contra DNS rebinding exige re-resolver no momento do scan
    (camada futura no executor, ver goal3).
    """
    if host.lower() in _FORBIDDEN_HOSTNAMES:
        return True
    if _is_ip_literal(host):
        return _ip_is_blocked(host)
    ips = _resolve_host_ips(host)
    if not ips:
        # FAIL CLOSED. `any([])` é False, então uma falha de DNS fazia a guarda de
        # SSRF liberar o host — a defesa se comportando como aprovação, que é o mesmo
        # defeito de "não rodou parece não achou", com consequência pior.
        # Bloquear não custa alvo legítimo: um host que não resolve não seria
        # escaneado de qualquer forma, e o que está na TARGET_ALLOWLIST é liberado
        # ANTES desta checagem (ver `validate_target_value`).
        return True
    return any(_ip_is_blocked(ip) for ip in ips)


def _host_in_allowlist(host: str, allowlist: list[str]) -> bool:
    """Confere se host (hostname ou IP) bate com algum entry da allowlist.

    Entries podem ser: hostname exato (`juice-shop`), CIDR (`10.0.0.0/8`),
    ou wildcard de domínio (`*.lab.example.com`).
    """
    host_l = host.lower()
    for entry in allowlist:
        entry_l = entry.strip().lower()
        if not entry_l:
            continue
        # CIDR?
        if "/" in entry_l:
            try:
                net = ipaddress.ip_network(entry_l, strict=False)
                ip = ipaddress.ip_address(host_l)
                if ip in net:
                    return True
            except ValueError:
                continue
        # wildcard?
        elif entry_l.startswith("*."):
            suffix = entry_l[2:]
            if host_l == suffix or host_l.endswith(f".{suffix}"):
                return True
        # match exato
        elif host_l == entry_l:
            return True
    return False


def validate_target_value(value: str, *, asset_type: str | None = None) -> str:
    """Valida e retorna `value` normalizado.

    Args:
        value: string controlada por user (CLI/API/UI input).
        asset_type: hint do tipo (`url`, `host`, `domain`, `repo`, `image`).
                    Quando `url`, parseia e valida scheme + host.

    Raises:
        TargetValidationError: motivo concreto da rejeição.

    Returns:
        valor normalizado (strip + lower do host quando aplicável).
    """
    if not value or not isinstance(value, str):
        raise TargetValidationError("target.value vazio ou tipo invalido")

    v = value.strip()

    # H4: bloqueia flags. argv injection: `-rf`, `--upload-pack=...`, etc.
    if v.startswith("-"):
        raise TargetValidationError(
            "target.value nao pode comecar com '-' (potencial injecao de flag em subprocess)"
        )

    # Extrair host conforme tipo. Ordem importa: asset_type ganha de heuristica de URL.
    host: str | None = None
    if asset_type == "repo":
        # Repo: URL git. Validar scheme http(s) ou ssh.
        if v.startswith(("http://", "https://")):
            return _validate_url_repo(v)
        if v.startswith("git@"):
            # `git@host:owner/repo` — o host fica entre o "@" e o ":".
            _guarda_de_rede(v[4:].split(":", 1)[0].split("/", 1)[0], rotulo="repo")
            return v
        raise TargetValidationError("repo deve usar http(s):// ou git@host:owner/repo (ssh)")
    elif asset_type == "image":
        # Image: registry/name:tag. SEC-04: se o primeiro componente for um host de
        # registry (tem "." ou ":") e apontar para rede interna/IMDS, bloquear —
        # senão `169.254.169.254/evil:latest` alcança o metadata pelo scanner.
        # Só há registry quando existe uma BARRA depois do primeiro componente.
        # `nginx:1.27-alpine` não tem registry — o `:` ali é a tag, não uma porta —
        # e a heurística antiga tratava `nginx` como host. Isso não incomodava
        # enquanto a resolução falhava ABERTA; com o fail-closed, passou a recusar
        # a imagem oficial mais comum do mundo. Regra do Docker: registry é o
        # primeiro componente SE contiver "." ou ":" ou for "localhost", E houver
        # "/" depois dele.
        first = v.split("/", 1)[0] if "/" in v else ""
        if first and ("." in first or ":" in first or first == "localhost"):
            registry_host = first.split(":", 1)[0]
            if (
                settings.LAB_ONLY
                and not _host_in_allowlist(registry_host, settings.target_allowlist)
                and _is_blocked_network(registry_host)
            ):
                raise TargetValidationError(
                    f"registry {registry_host!r} em rede privada/loopback/IMDS "
                    "e nao esta em TARGET_ALLOWLIST"
                )
        return v
    elif asset_type == "url" or "://" in v:
        try:
            parsed = urlparse(v)
        except ValueError as e:
            raise TargetValidationError(f"URL malformada: {e}") from e
        if parsed.scheme not in {"http", "https"}:
            raise TargetValidationError(
                f"scheme '{parsed.scheme}' nao permitido (apenas http/https)"
            )
        if not parsed.hostname:
            raise TargetValidationError("URL sem hostname")
        host = parsed.hostname
    elif asset_type in {"host", "domain"}:
        # Pode vir com :porta — extrair só hostname
        host = v.split(":", 1)[0] if ":" in v and not v.count(":") > 1 else v
        host = host.split("/", 1)[0]  # tira path se vier coloando
        if not _HOSTNAME_RE.match(host) and not _is_ip_literal(host):
            raise TargetValidationError(f"hostname/IP malformado: {host!r}")

    # H5: SSRF — bloqueia hosts privados/loopback fora da allowlist quando LAB_ONLY=true.
    # Mesmo caminho que REPO usa (`_guarda_de_rede`): a duplicata anterior era o que
    # deixava um tipo de alvo inteiro de fora do controle.
    if host is not None:
        _guarda_de_rede(host, rotulo="host")

    return v


def _is_ip_literal(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def _validate_url_repo(url: str) -> str:
    """Valida repo url: sem credencial embutida (vaza em log) E com host no escopo.

    O guarda de rede FALTAVA aqui. `asset_type="repo"` retornava antes do gate H5, e
    REPO é justamente o tipo que vai direto para `git clone <target.value>` e
    `trufflehog git <target.value>` a partir do worker, dentro da rede interna.
    Medido antes do conserto, com LAB_ONLY=true e allowlist vazia:

        repo  https://169.254.169.254/x/y.git   -> ACEITO
        repo  http://127.0.0.1:3000/a/b.git     -> ACEITO
        repo  https://postgres/x/y.git          -> ACEITO
        url   http://127.0.0.1:8080/            -> RECUSADO

    A assimetria ficou pior quando url/host/image ganharam fail-closed: um operador
    com `scans:run` alcançava o Gitea/GitLab interno e os serviços da rede do banco,
    e o "coração do compliance gate" não via.
    """
    parsed = urlparse(url)
    if parsed.username or parsed.password:
        raise TargetValidationError(
            "URL de repo nao deve conter credenciais embutidas (use SSH key ou GITHUB_TOKEN env)"
        )
    _guarda_de_rede(parsed.hostname or "", rotulo="repo")
    return url


def _guarda_de_rede(host: str, *, rotulo: str) -> None:
    """Aplica o gate H5 (LAB_ONLY + allowlist + rede bloqueada) a um host qualquer.

    Extraído para que REPO use exatamente o mesmo caminho de URL e HOST — a duplicata
    anterior era o que deixava um tipo de alvo de fora.
    """
    if not host:
        raise TargetValidationError(f"{rotulo}: nao consegui extrair o host do alvo")
    if not settings.LAB_ONLY:
        return
    if _host_in_allowlist(host, settings.target_allowlist):
        return
    if _is_blocked_network(host):
        raise TargetValidationError(_motivo_bloqueio(host, rotulo))


def _motivo_bloqueio(host: str, rotulo: str) -> str:
    """Diz o que REALMENTE aconteceu.

    A mensagem única acusava todo host de estar "em rede privada/loopback/IMDS",
    inclusive quando o motivo real era "não consegui resolver o nome". Numa rede
    corporativa sem DNS externo — o ambiente-alvo — isso mandaria o operador caçar um
    problema de escopo que não existe.
    """
    if not _is_ip_literal(host) and not _resolve_host_ips(host):
        return (
            f"{rotulo} {host!r} nao resolve em DNS e nao esta em TARGET_ALLOWLIST. "
            "Alvo que nao resolve e recusado por precaucao (fail closed): sem resolver, "
            "nao da para saber se ele aponta para a rede interna. Se o alvo e legitimo, "
            "confira o DNS do container ou adicione o host a TARGET_ALLOWLIST."
        )
    return f"{rotulo} {host!r} em rede privada/loopback/IMDS e nao esta em TARGET_ALLOWLIST"
