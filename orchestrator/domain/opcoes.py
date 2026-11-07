"""As opções de scanner que a API aceita, campo a campo.

`ScanIn.options` era um `dict` livre que ia direto para o adapter. `nmap_args` virava
argv do nmap (`--script` com NSE de um caminho, `-oN /data/secrets/...`, alvos extras
fora do escopo), `nuclei.templates` virava `-t` livre e `semgrep.config` aceitava
caminho do disco: um operator (papel com `scans:run`) chegava a arquivo e rede que o
escopo existe para fechar (revisão de segurança de 07/11/2026).

Agora cada scanner tem a lista do que pode vir de fora, com tipo e faixa. O resto é
recusado com o nome do campo, em vez de ignorado em silêncio: quem mandou precisa saber
que não valeu.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


class OpcaoRecusada(ValueError):
    """Opção de scanner fora do que a API aceita."""


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    raise OpcaoRecusada("tem que ser true ou false")


def _int(minimo: int, maximo: int) -> Callable[[Any], int]:
    def f(v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int | str):
            raise OpcaoRecusada(f"tem que ser inteiro entre {minimo} e {maximo}")
        try:
            n = int(v)
        except ValueError as e:
            raise OpcaoRecusada(f"tem que ser inteiro entre {minimo} e {maximo}") from e
        if not minimo <= n <= maximo:
            raise OpcaoRecusada(f"tem que ser inteiro entre {minimo} e {maximo}")
        return n

    return f


def _lista_de(permitidos: frozenset[str]) -> Callable[[Any], str]:
    """CSV (ou lista) com valores de um conjunto fechado."""

    def f(v: Any) -> str:
        itens = v if isinstance(v, list) else str(v).split(",")
        limpos = [str(i).strip().lower() for i in itens if str(i).strip()]
        if not limpos or any(i not in permitidos for i in limpos):
            raise OpcaoRecusada(f"valores aceitos: {', '.join(sorted(permitidos))}")
        return ",".join(limpos)

    return f


def _texto(padrao: str, maximo: int = 200) -> Callable[[Any], str]:
    rx = re.compile(padrao)

    def f(v: Any) -> str:
        if not isinstance(v, str) or len(v) > maximo or not rx.fullmatch(v):
            raise OpcaoRecusada("formato não aceito")
        return v

    return f


def _textos(padrao: str, maximo_itens: int = 50) -> Callable[[Any], list[str]]:
    um = _texto(padrao)

    def f(v: Any) -> list[str]:
        if not isinstance(v, list) or len(v) > maximo_itens:
            raise OpcaoRecusada(f"tem que ser lista com até {maximo_itens} itens")
        return [um(i) for i in v]

    return f


_SEVERIDADES = frozenset({"info", "low", "medium", "high", "critical"})
_SEVERIDADES_TRIVY = frozenset({"unknown", "low", "medium", "high", "critical"})
_UUID = r"[0-9a-fA-F-]{36}"
# Texto livre de consulta OSINT/dork: sem caractere de controle, sem começar com "-".
_CONSULTA = r"[^\x00-\x1f\-][^\x00-\x1f]*"

ACEITAS: dict[str, dict[str, Callable[[Any], Any]]] = {
    "zap": {"active": _bool, "ajax": _bool, "max_children": _int(1, 100)},
    "nmap": {},
    "nuclei": {"rate_limit": _int(1, 500), "severity": _lista_de(_SEVERIDADES)},
    "trivy": {
        "severity": _lista_de(_SEVERIDADES_TRIVY),
        "scanners": _lista_de(frozenset({"vuln", "secret", "misconfig", "license"})),
    },
    # Só pacote do registro (`p/...`) ou `auto`: caminho de disco e URL ficam de fora.
    "semgrep": {
        "config": _textos(r"auto|p/[a-z0-9][a-z0-9._-]{0,80}", 10),
        "clone_depth": _int(0, 1000),
    },
    "gitleaks": {"clone_depth": _int(0, 1000)},
    "checkov": {
        "framework": _texto(r"[a-z0-9_]{1,40}"),
        "clone_depth": _int(0, 1000),
    },
    "trufflehog": {"only_verified": _bool, "since_commit": _texto(r"[0-9a-fA-F]{7,40}")},
    "dnstwist": {"ssdeep": _bool},
    "github_exposure": {"dorks": _textos(_CONSULTA, 20), "max_results_per_dork": _int(1, 100)},
    "censys": {"query": _texto(_CONSULTA, 500), "pages": _int(1, 10)},
    "shodan": {"query": _texto(_CONSULTA, 500), "limit": _int(1, 1000)},
    "greenbone": {
        "config_id": _texto(_UUID),
        "scanner_id": _texto(_UUID),
        "port_list_id": _texto(_UUID),
    },
    "kube_bench": {"targets": _lista_de(frozenset({"master", "node", "etcd", "policies"}))},
}


def opcoes_seguras(options: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Valida `options` contra `ACEITAS` e devolve a versão normalizada.

    Levanta `OpcaoRecusada` com `scanner.campo` no texto para o primeiro problema.
    """
    if not options:
        return {}
    if not isinstance(options, dict):
        raise OpcaoRecusada("options tem que ser um objeto {scanner: {campo: valor}}")
    out: dict[str, dict[str, Any]] = {}
    for scanner, campos in options.items():
        regras = ACEITAS.get(scanner)
        if regras is None:
            raise OpcaoRecusada(f"options.{scanner}: scanner sem opções configuráveis")
        if not isinstance(campos, dict):
            raise OpcaoRecusada(f"options.{scanner} tem que ser um objeto")
        limpo: dict[str, Any] = {}
        for campo, valor in campos.items():
            regra = regras.get(campo)
            if regra is None:
                aceitos = ", ".join(sorted(regras)) or "nenhum"
                raise OpcaoRecusada(f"options.{scanner}.{campo} não é aceito (aceitos: {aceitos})")
            try:
                limpo[campo] = regra(valor)
            except OpcaoRecusada as e:
                raise OpcaoRecusada(f"options.{scanner}.{campo}: {e}") from e
        out[scanner] = limpo
    return out
