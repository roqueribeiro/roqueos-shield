#!/usr/bin/env python3
"""Regenera todos os diagramas de docs/assets/diagramas/.

    python scripts/gen_diagrams.py            # gera tudo
    python scripts/gen_diagrams.py --check    # nao escreve, so confere se esta em dia

O `--check` existe para o CI: diagrama versionado que ninguem consegue refazer vira
uma foto antiga da arquitetura pendurada no README. Se o codigo do diagrama mudou e
o SVG nao foi regerado, o check reprova.

Nao depende de nada fora da biblioteca padrao. A medida de texto vem de
scripts/diagrams/metrics.json, uma tabela de avanco por caractere extraida das
fontes reais e versionada junto: assim o mesmo codigo gera o mesmo SVG em
qualquer maquina, com ou sem a fonte instalada.

Cada modulo sai em dois idiomas e dois temas, quatro arquivos por diagrama:

    <nome>.claro.svg  <nome>.escuro.svg          portugues
    <nome>.en.claro.svg  <nome>.en.escuro.svg    ingles

O texto de cada idioma e um par tr("pt", "en") dentro do proprio modulo.
"""

from __future__ import annotations

import argparse
import sys

# Cache de bytecode e um jeito silencioso de o check validar a coisa errada:
# restaurar um .py mutado no MESMO segundo do .pyc faz o Python reusar o bytecode
# antigo, e o --check passa comparando o SVG com o codigo que nao esta mais la.
# Aconteceu de verdade no teste de mutacao. Nao escrever cache elimina a classe.
sys.dont_write_bytecode = True

from pathlib import Path  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "docs" / "assets" / "diagramas"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagrams import (  # noqa: E402
    c4lib,  # noqa: E402
    d01_context,
    d02_containers,
    d03_components,
    d04_code,
    d05_infra,
    d06_esteira,
    d07_kali,
    d08_integracoes,
    d09_telas,
)

MODULOS = [
    d01_context,
    d02_containers,
    d03_components,
    d04_code,
    d05_infra,
    d06_esteira,
    d07_kali,
    d08_integracoes,
    d09_telas,
]
TEMAS = [(c4lib.LIGHT, "claro"), (c4lib.DARK, "escuro")]
# portugues sem marca no nome, ingles com ".en": o par que o README referencia.
IDIOMAS = [("pt", ""), ("en", ".en")]


def gerar() -> dict[str, str]:
    saidas: dict[str, str] = {}
    try:
        for lingua, marca in IDIOMAS:
            c4lib.set_lang(lingua)
            for mod in MODULOS:
                for tema, sufixo in TEMAS:
                    saidas[f"{mod.SAIDA}{marca}.{sufixo}.svg"] = mod.draw(tema).render()
    finally:
        c4lib.set_lang("pt")
    return saidas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check", action="store_true", help="nao escreve; sai 1 se algum SVG estiver desatualizado"
    )
    args = ap.parse_args()

    SAIDA.mkdir(parents=True, exist_ok=True)
    saidas = gerar()

    if args.check:
        problemas = []
        for nome, conteudo in saidas.items():
            alvo = SAIDA / nome
            if not alvo.exists():
                problemas.append(f"  FALTA      {alvo.relative_to(RAIZ)}")
            elif alvo.read_text(encoding="utf-8") != conteudo:
                problemas.append(f"  DESATUALIZADO  {alvo.relative_to(RAIZ)}")
        # Orfao: arquivo na pasta que o gerador nao produz. Diagrama renomeado deixa
        # o antigo para tras, e o README continua apontando para uma foto que ninguem
        # mais refaz. Vale para qualquer arquivo, nao so .svg.
        extras = {p.name for p in SAIDA.iterdir() if p.is_file()} - set(saidas)
        for e in sorted(extras):
            problemas.append(f"  ORFAO      {(SAIDA / e).relative_to(RAIZ)}")
        if problemas:
            print(
                "Diagramas fora de sincronia com scripts/diagrams/:\n"
                + "\n".join(problemas)
                + "\n\nRode: python scripts/gen_diagrams.py",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {len(saidas)} diagramas em dia.")
        return 0

    for nome, conteudo in saidas.items():
        (SAIDA / nome).write_text(conteudo, encoding="utf-8")
    print(f"OK: {len(saidas)} diagramas gerados em {SAIDA.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
