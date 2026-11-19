"""Empacota uma árvore de código para `POST /code/{projeto}/uploads`.

Roda na máquina de quem chama (notebook, CI, sessão de agente), não no shield.

Num repositório git, entra o que o git entregaria num commit agora: arquivos
rastreados mais os não rastreados que o `.gitignore` não ignora (`git ls-files -co
--exclude-standard`). Assim `node_modules/`, `.venv/` e `.env` ficam de fora pelo
mesmo critério que o projeto já usa, e o código ainda não commitado entra. Fora de um
git, entra tudo menos `.git/`.

A pasta `.git` nunca vai: o histórico não é enviado (o relatório declara essa lacuna)
e o servidor recusa um envio que a traga.
"""

from __future__ import annotations

import io
import os
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path


class EmpacotamentoFalhou(RuntimeError):
    pass


@dataclass(frozen=True)
class Pacote:
    dados: bytes
    arquivos: int


# Checkout montado num container com outro dono (o caso do CI: `-v "$PWD:/src"`) faz o
# git recusar a pasta por "dubious ownership". Sem isto o `rev-parse` falha, o
# empacotador cai para "tudo menos .git" e leva `.env` e `node_modules/` junto. Só
# lemos a pasta (ls-files), nunca rodamos hook ou config dela.
_SEGURO = ["-c", "safe.directory=*", "-c", "core.fsmonitor=false"]


def _do_git(raiz: Path) -> list[str] | None:
    r = subprocess.run(  # noqa: S603
        ["git", *_SEGURO, "-C", str(raiz), "rev-parse", "--show-prefix"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return None
    lista = subprocess.run(  # noqa: S603
        [
            "git",
            *_SEGURO,
            "-C",
            str(raiz),
            "ls-files",
            "-co",
            "--exclude-standard",
            "-z",
            "--",
            ".",
        ],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if lista.returncode != 0:
        raise EmpacotamentoFalhou(f"git ls-files falhou: {lista.stderr.decode(errors='replace')}")
    return [p for p in lista.stdout.decode().split("\0") if p]


def _andando(raiz: Path) -> list[str]:
    nomes: list[str] = []
    for pasta, subpastas, arquivos in os.walk(raiz):
        subpastas[:] = [d for d in subpastas if d != ".git"]
        for a in arquivos:
            nomes.append(str((Path(pasta) / a).relative_to(raiz)))
    return nomes


def listar(raiz: Path) -> list[str]:
    nomes = _do_git(raiz)
    if nomes is None:
        nomes = _andando(raiz)
    # Arquivo listado pelo git e apagado do disco (rastreado, removido sem commit) não
    # existe para escanear; `.git` dentro de submódulo também não vai. Link simbólico
    # fica de fora: um que aponte para fora da árvore faria o servidor recusar o envio
    # inteiro, e o alvo do link, se for da árvore, já entra por si.
    return sorted(
        n
        for n in nomes
        if ".git" not in Path(n).parts and not (raiz / n).is_symlink() and (raiz / n).is_file()
    )


def empacotar(raiz: Path) -> Pacote:
    raiz = raiz.resolve()
    if not raiz.is_dir():
        raise EmpacotamentoFalhou(f"{raiz} não é uma pasta")
    nomes = listar(raiz)
    if not nomes:
        raise EmpacotamentoFalhou(
            f"nenhum arquivo para enviar em {raiz} (tudo ignorado pelo .gitignore?)"
        )
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for n in nomes:
            tar.add(raiz / n, arcname=n, recursive=False)
    return Pacote(dados=buf.getvalue(), arquivos=len(nomes))
