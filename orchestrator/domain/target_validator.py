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


class AlvoForaDoEscopo(TargetValidationError):
    """O host é de rede interna (ou não resolve) e não está em TARGET_ALLOWLIST.

    Separada do erro genérico para a tela poder explicar e oferecer o caminho certo
    (liberar no escopo, ou trocar `localhost` por `host.docker.internal`) em vez de
    "não foi possível iniciar o scan". `motivo` é `rede_local` ou `nao_resolve`;
    `loopback` diz se o host é o próprio container, que não se libera pela tela.
    """

    def __init__(self, mensagem: str, *, host: str, motivo: str, loopback: bool) -> None:
        super().__init__(mensagem)
        self.host = host
        self.motivo = motivo
        self.loopback = loopback


# Domínios/IPs que NÃO podem ser alvo quando LAB_ONLY=true sem allowlist explícita.
# RFC1918, loopback, link-local, IMDS, ULA IPv6.
_FORBIDDEN_HOSTNAMES: frozenset[str] = frozenset(
    {"localhost", "metadata.google.internal", "metadata", "instance-data"}
)

_HOSTNAME_RE = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
)


# Faixas internas que o `is_private` do Python não marca: CGNAT (é a rede do
# Tailscale, comum em homelab), benchmarking, NAT64 e 6to4 (os dois últimos embrulham
# um IPv4, inclusive 127.0.0.1).
_FAIXAS_EXTRAS = tuple(
    ipaddress.ip_network(n)
    for n in ("100.64.0.0/10", "198.18.0.0/15", "64:ff9b::/96", "64:ff9b:1::/48", "2002::/16")
)


def _ipv4_embutido(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | None:
    """O IPv4 dentro de um IPv6 mapeado, NAT64 ou 6to4."""
    if not isinstance(ip, ipaddress.IPv6Address):
        return None
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip.sixtofour:
        return ip.sixtofour
    # NAT64 bem-conhecido (/96) e o local (64:ff9b:1::/48, RFC 8215): o IPv4 vem nos
    # últimos 32 bits nas duas formas usuais de tradutor.
    if ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("64:ff9b:1::/48"):
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


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
        or any(ip in n for n in _FAIXAS_EXTRAS if n.version == ip.version)
    )


def _classe_sensivel(ip_str: str) -> str | None:
    """`link_local` (metadata de nuvem), `loopback`, ou None."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return None
    v4 = _ipv4_embutido(ip)
    if v4 is not None:
        ip = v4
    if ip.is_link_local or ip.is_unspecified:
        return "link_local"
    if ip.is_loopback:
        return "loopback"
    return None


def _guarda_dura(host: str, rotulo: str) -> None:
    """O que nem LAB_ONLY=false nem um NOME na allowlist abrem.

    - Link-local (169.254.169.254, o metadata da nuvem): nunca.
    - Loopback: só quando a allowlist traz o próprio endereço (`127.0.0.1`,
      `127.0.0.0/8`, `::1` ou `localhost`), que é decisão explícita de quem roda o
      shield fora de container. Por NOME liberado, não: a allowlist guarda o nome, e
      um nome liberado quando resolvia para a rede da casa pode passar a resolver para
      127.0.0.1 depois (DNS rebinding). Dentro do container, loopback é o próprio
      shield: API, Redis e ZAP.
    """
    nu = host.strip("[]")
    # A exceção do loopback vale só para o endereço DIRETO (127.x, ::1, localhost) na
    # allowlist: um IPv6 que embrulha 127.0.0.1 (NAT64, 6to4, mapeado) não é a forma
    # que alguém escreve de propósito.
    embrulhado = _is_ip_literal(nu) and _ipv4_embutido(ipaddress.ip_address(nu)) is not None
    literal = (_is_ip_literal(nu) and not embrulhado) or nu.lower() == "localhost"
    ips = (
        ["127.0.0.1"]
        if nu.lower() == "localhost"
        else ([nu] if _is_ip_literal(nu) else _resolve_host_ips(nu))
    )
    classes = {c for c in (_classe_sensivel(ip) for ip in ips) if c}
    if "link_local" in classes:
        motivo = "é link-local (o metadata da nuvem) e não pode ser alvo"
    elif "loopback" in classes and not (
        literal and _host_in_allowlist(nu, settings.target_allowlist)
    ):
        motivo = (
            "é loopback (dentro do container, o próprio RoqueShield) e só vira alvo com o "
            "próprio endereço na allowlist"
        )
    else:
        return
    raise AlvoForaDoEscopo(
        f"{rotulo} {host!r} {motivo}", host=host, motivo="rede_local", loopback=True
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

    # Barra invertida, espaço e controle: o `urlparse` do Python e o WHATWG (Firefox do
    # ZAP, Chrome) discordam sobre o host de `http://127.0.0.1:8090\\@exemplo.com/`.
    # O validador via exemplo.com e o navegador ia ao ZAP. Não existe alvo legítimo
    # com esses caracteres, então eles não passam.
    if any(c == "\\" or c.isspace() or ord(c) < 0x20 or ord(c) == 0x7F for c in v):
        raise TargetValidationError(
            "target.value com barra invertida, espaço ou caractere de controle"
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
            # `[::1]:5000` tem o host entre colchetes; `host:5000` antes do último `:`.
            # Cortar no primeiro `:` deixava `[` como host de um IPv6 (revisão do PR #20).
            if first.startswith("["):
                registry_host = first[1 : first.find("]")] if "]" in first else ""
            else:
                registry_host = first.rsplit(":", 1)[0] if first.count(":") == 1 else first
            if not registry_host or (
                not _HOSTNAME_RE.match(registry_host) and not _is_ip_literal(registry_host)
            ):
                raise TargetValidationError(f"registry malformado em {v!r}")
            # Loopback e metadata nem com LAB_ONLY=false (o mesmo dos outros tipos).
            _guarda_dura(registry_host, "registry")
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
    elif asset_type == "port":
        # `host:porta/proto`, `[v6]:porta/proto`. Ficava sem host e pulava a guarda
        # inteira: `127.0.0.1:6379/tcp` mandava o nmap no Redis do próprio container.
        base = v.split("/", 1)[0]
        if base.startswith("["):
            host = base[1 : base.find("]")] if "]" in base else ""
        else:
            host = base.rsplit(":", 1)[0] if ":" in base else base
        if not host or (not _HOSTNAME_RE.match(host) and not _is_ip_literal(host)):
            raise TargetValidationError(f"porta malformada (use host:porta/proto): {v!r}")
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
    _guarda_dura(host, rotulo)
    if not settings.LAB_ONLY:
        return
    if _host_in_allowlist(host, settings.target_allowlist):
        return
    if _is_blocked_network(host):
        nao_resolve = not _is_ip_literal(host) and host.lower() not in _FORBIDDEN_HOSTNAMES
        nao_resolve = nao_resolve and not _resolve_host_ips(host)
        raise AlvoForaDoEscopo(
            _motivo_bloqueio(host, rotulo),
            host=host,
            motivo="nao_resolve" if nao_resolve else "rede_local",
            loopback=_e_loopback(host),
        )


def liberavel_pela_tela(erro: AlvoForaDoEscopo) -> bool:
    """A tela pode oferecer "liberar no escopo" para este host?

    Só para `motivo == "rede_local"` com host que não é sensível. Não oferece para:

    - nome que não resolve (liberar não faz ele resolver);
    - os nomes de `_FORBIDDEN_HOSTNAMES` (`localhost`, `metadata`,
      `metadata.google.internal`, `instance-data`), pelo nome, resolvam ou não;
    - host cujo IP (literal ou resolvido, com IPv4 embutido em NAT64/6to4/mapeado
      desembrulhado) é link-local (169.254.0.0/16, fe80::/10, onde mora o metadata da
      nuvem), não especificado (0.0.0.0, ::) ou loopback (o próprio container).

    Isto é só o atalho da tela. Link-local e não especificado não viram alvo de jeito
    nenhum: `_guarda_dura` os recusa mesmo com `LAB_ONLY=false` ou na allowlist.
    Loopback vira alvo só com o próprio endereço (`127.0.0.1`, `::1`, `localhost`) na
    `TARGET_ALLOWLIST`, nunca por nome liberado. O resto da rede interna (RFC1918,
    CGNAT, ULA) o operador libera pela allowlist ou com `LAB_ONLY=false`.
    """
    if erro.motivo != "rede_local":
        return False
    h = erro.host.lower().strip("[]")
    if h in _FORBIDDEN_HOSTNAMES:
        return False
    ips = [h] if _is_ip_literal(h) else _resolve_host_ips(h)
    # Com o IPv4 embutido desembrulhado: o NAT64 de 127.0.0.1 é loopback.
    return not any(_classe_sensivel(s) for s in ips)


def _e_loopback(host: str) -> bool:
    """O próprio container: `localhost`, 127.0.0.0/8, ::1, 0.0.0.0."""
    h = host.lower().strip("[]")
    if h == "localhost" or h.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


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
