---
description: Roda pytest (todos os testes ou alvo específico)
allowed-tools: Bash
argument-hint: "[caminho/teste/opcional.py]"
---

Roda a suíte no checkout (a imagem do orchestrator não leva `tests/` nem pytest). Se
`$ARGUMENTS` for vazio, roda todos. Senão, roda só o alvo.

```bash
make test ARGS="$ARGUMENTS"
```

Para rodar com cobertura, com o piso do CI:
```bash
uv run --frozen --extra dev pytest --cov=orchestrator --cov-report=term-missing --cov-fail-under=64
```

Reporte: total de testes, falhas, % de cobertura (se aplicável).
