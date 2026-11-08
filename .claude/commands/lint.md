---
description: Roda ruff (check + format --check) e mypy no checkout
allowed-tools: Bash
argument-hint: ""
---

Lint + type check, no checkout (a imagem do orchestrator não tem ruff, mypy nem
`tests/`: é buildada com `--no-dev`):

```bash
make lint        # ruff check + ruff format --check em orchestrator, tests e scripts, como o CI
make typecheck   # mypy orchestrator (no CI ainda não bloqueia o merge)
```

Para auto-fix:

```bash
uv run --frozen --extra dev ruff format orchestrator tests scripts
uv run --frozen --extra dev ruff check --fix orchestrator tests scripts
```

Reporte número de erros/warnings por categoria.
