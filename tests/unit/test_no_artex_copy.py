"""Goal 0.2: o tripwire de origem pega cópia literal do ARTEX, e só isso.

Mutante do mecanismo: marca inequívoca do ARTEX casa; palavra comum que contém
"artex" como substring não casa; o repo de hoje está limpo.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _carregar() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_no_artex_copy_sob_teste", ROOT / "scripts" / "check_no_artex_copy.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pega_import_do_sdk_do_artex() -> None:
    mod = _carregar()
    assert mod.marcas_de_artex('import "github.com/Autumn-27/norma"')


def test_pega_ua_do_enrich() -> None:
    mod = _carregar()
    assert "artex-enrich" in " ".join(mod.marcas_de_artex("User-Agent: artex-enrich/1.0"))


def test_nao_casa_com_palavra_que_contem_artex_como_substring() -> None:
    # "copiarTexto" e "startExecution" contêm "artex"; as marcas reais, não.
    mod = _carregar()
    comum = "export async function copiarTexto() { startExecution() }"
    assert mod.marcas_de_artex(comum) == []


def test_repo_esta_limpo_hoje() -> None:
    mod = _carregar()
    assert mod.varrer() == []
