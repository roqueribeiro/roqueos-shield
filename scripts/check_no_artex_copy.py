#!/usr/bin/env python3
"""Tripwire de origem: pega cópia LITERAL de código do ARTEX no nosso.

O plano de fusão (claude/roqueshield_plano_aprendizado_artex_2026-11-15.md, no
Project) reimplementa IDEIAS do ARTEX (github.com/Autumn-27/ARTEX, AGPL-3.0); o
RoqueShield é Apache-2.0, e copiar arquivo ou trecho obrigaria a relicenciar.

Este gate NÃO substitui a revisão humana — ele só pega o acidente óbvio: um
identificador, caminho de import ou moldura que só existe no ARTEX apareceu no
nosso código. Pega cópia literal, não cópia reescrita. O controle de verdade
continua sendo a revisão de quem traz a ideia.

Varre orchestrator/ e web/src/ (menos i18n/, que é multilíngue de propósito).
Rodar: python scripts/check_no_artex_copy.py (exit != 0 reprova).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Marcas que só existem no ARTEX: caminho do SDK `norma`, UAs próprios do enrich e
# do self-update, o UA da WebFetch do SDK, e a moldura do guard em chinês. Nada
# disso aparece no RoqueShield legítimo. "artex" cru NÃO entra (casa com
# "copiarTexto"/"startExecution"); marcador chinês genérico como 内置 NÃO entra (a
# tradução zh-CN do RoqueShield o usa de verdade).
_MARCAS = (
    r"Autumn-?27",
    r"github\.com/Autumn",
    r"artex-enrich",
    r"artex-selfupdate",
    r"norma/0\.4",
    r"平台管控·非目标防御",
)
_RX = re.compile("|".join(_MARCAS), re.IGNORECASE)
_EXTS = (".py", ".js", ".ts", ".vue", ".mjs")


def marcas_de_artex(texto: str) -> list[str]:
    """Marcas inequívocas do ARTEX achadas no texto (lista vazia = limpo)."""
    return sorted({m.group(0) for m in _RX.finditer(texto)})


def _codigo_rastreado() -> list[str]:
    saida = subprocess.run(
        ["git", "ls-files", "orchestrator", "web/src"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [a for a in saida if "/i18n/" not in a and a.endswith(_EXTS)]


def varrer() -> list[tuple[str, list[str]]]:
    achados: list[tuple[str, list[str]]] = []
    for arq in _codigo_rastreado():
        try:
            texto = (ROOT / arq).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        marcas = marcas_de_artex(texto)
        if marcas:
            achados.append((arq, marcas))
    return achados


def main() -> int:
    achados = varrer()
    if not achados:
        print("origem ok: nenhuma marca literal do ARTEX no código (orchestrator/, web/src/).")
        return 0
    print("CÓPIA LITERAL DO ARTEX NO CÓDIGO — o ARTEX é AGPL-3.0, o RoqueShield é Apache-2.0:\n")
    for arq, marcas in achados:
        print(f"  {arq}: {', '.join(marcas)}")
    print(f"\n{len(achados)} arquivo(s). Reimplemente a ideia; não copie o arquivo.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
