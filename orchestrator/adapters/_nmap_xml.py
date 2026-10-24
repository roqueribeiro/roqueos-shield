"""Parser do XML do nmap com `defusedxml` (GOAL-SHIELD-02, Issue #13).

Substitui o `python-libnmap`, que parseia com o `xml` da stdlib e carrega o
CVE-2022-30284 (XXE): um XML de nmap adulterado podia ler arquivo local do
orchestrator. O `defusedxml` recusa DTD com entidade, entidade externa e o
"billion laughs" antes de montar a árvore.

Lê só o que o adapter usa: endereço, nomes, e por porta o protocolo, o estado, o
serviço e o banner (produto, versão e extra que o `-sV` preenche).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

# Nó da árvore. Sem importar o `xml` da stdlib aqui: tudo passa pelo defusedxml.
Element = Any


class NmapXmlError(ValueError):
    """O XML não é um relatório do nmap legível (truncado, adulterado, outro formato)."""


@dataclass(frozen=True)
class NmapService:
    port: int
    protocol: str
    state: str
    service: str
    banner: str


@dataclass(frozen=True)
class NmapHost:
    address: str
    hostnames: list[str] = field(default_factory=list)
    services: list[NmapService] = field(default_factory=list)


# Mesma preferência do libnmap: IPv4, depois IPv6, depois MAC.
_ORDEM_DE_ENDERECO = ("ipv4", "ipv6", "mac")


def _endereco(host: Element) -> str:
    por_tipo = {a.get("addrtype", ""): a.get("addr", "") for a in host.findall("address")}
    for tipo in _ORDEM_DE_ENDERECO:
        if por_tipo.get(tipo):
            return por_tipo[tipo]
    return next((v for v in por_tipo.values() if v), "")


def _servico(porta: Element) -> NmapService:
    estado = porta.find("state")
    svc = porta.find("service")
    nome = svc.get("name", "") if svc is not None else ""
    banner = (
        " ".join(v for v in (svc.get(k, "") for k in ("product", "version", "extrainfo")) if v)
        if svc is not None
        else ""
    )
    return NmapService(
        port=int(porta.get("portid", "0")),
        protocol=porta.get("protocol", ""),
        state=estado.get("state", "") if estado is not None else "",
        service=nome,
        banner=banner,
    )


def parse_nmap_xml(texto: str) -> list[NmapHost]:
    """Os hosts do relatório. Levanta `NmapXmlError` para qualquer coisa ilegível."""
    try:
        raiz = fromstring(texto, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException) as e:
        raise NmapXmlError(str(e) or type(e).__name__) from e
    if raiz.tag != "nmaprun":
        raise NmapXmlError(f"raiz <{raiz.tag}> não é <nmaprun>")
    hosts = []
    for h in raiz.findall("host"):
        try:
            servicos = [_servico(p) for p in h.findall("ports/port")]
        except ValueError as e:  # portid que não é número
            raise NmapXmlError(f"porta ilegível: {e}") from e
        hosts.append(
            NmapHost(
                address=_endereco(h),
                hostnames=[n.get("name", "") for n in h.findall("hostnames/hostname")],
                services=servicos,
            )
        )
    return hosts
