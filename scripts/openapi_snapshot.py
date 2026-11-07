"""Fotografia do contrato da API em `docs/openapi.json`.

Por que existe: a tela do RoqueOS fala com esta API por um proxy pass-through, e a
tela do standalone e a CLI também. Mudança de rota ou de campo sem ninguém ver só
aparecia na tela do usuário. Com a fotografia no repo, toda mudança de contrato vira
diff revisável, e o teste `test_openapi_snapshot.py` reprova quando o código muda a API
sem atualizar a fotografia.

    python scripts/openapi_snapshot.py --write   # depois de mudar a API de propósito
    python scripts/openapi_snapshot.py --check   # o que o teste faz
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "docs" / "openapi.json"


def gerar() -> str:
    sys.path.insert(0, str(RAIZ))
    from orchestrator.main import app

    return json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    atual = gerar()
    if "--write" in sys.argv:
        ARQUIVO.write_text(atual, encoding="utf-8")
        print(f"escrito {ARQUIVO.relative_to(RAIZ)}")
        return 0
    guardado = ARQUIVO.read_text(encoding="utf-8") if ARQUIVO.exists() else ""
    if guardado != atual:
        print(
            "a API mudou e docs/openapi.json não: rode `python scripts/openapi_snapshot.py --write`"
        )
        return 1
    print("docs/openapi.json em dia")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
