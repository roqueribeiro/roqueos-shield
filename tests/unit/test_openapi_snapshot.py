"""O contrato da API só muda com a fotografia junto (ver scripts/openapi_snapshot.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _modulo():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "openapi_snapshot", RAIZ / "scripts" / "openapi_snapshot.py"
    )
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_api_bate_com_a_fotografia() -> None:
    m = _modulo()
    guardado = m.ARQUIVO.read_text(encoding="utf-8")
    assert guardado == m.gerar(), (
        "a API mudou e docs/openapi.json não. Se foi de propósito: "
        "python scripts/openapi_snapshot.py --write, e revise o diff"
    )


def test_swagger_tem_o_botao_authorize() -> None:
    import json

    esquemas = json.loads(_modulo().gerar())["components"]["securitySchemes"]
    assert esquemas["ApiToken"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Token",
        "description": esquemas["ApiToken"]["description"],
    }
