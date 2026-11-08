---
description: Convenções de testes (pytest, fixtures, async)
paths:
  - "tests/**"
  - "**/test_*.py"
  - "**/*_test.py"
  - "conftest.py"
---

# Convenções de testes

## Setup

- pytest + pytest-asyncio (`asyncio_mode = "auto"` em `pyproject.toml`)
- Coverage via `--cov=orchestrator`
- Rodar via `make test`, que roda **no checkout**, não no container: `uv run --frozen --extra dev pytest -q tests/`. A imagem não leva `tests/` nem as dependências de dev (o Dockerfile instala com `--no-dev`), então `docker compose run ... pytest` não funciona.
- Alvo específico: `make test ARGS=tests/unit/test_scrubber.py`. Sem uv, com o venv já criado: `.venv/bin/pytest -q tests/`.
- `make lint` (ruff check + ruff format --check) e `make typecheck` (mypy) também rodam no checkout pelo mesmo `uv run --frozen --extra dev`.

## Estrutura

```
tests/
├── unit/                  # rápidos, sem rede, sem DB
│   ├── test_scrubber.py
│   ├── test_schemas.py
│   ├── test_dedup.py
│   └── test_compliance.py
├── integration/           # contra ZAP/Greenbone via compose (lentos)
└── fixtures/              # XMLs/JSONs reais de scanners pra normalizers testarem
```

## Padrões

### Unit
- Funções puras, schemas Pydantic, scrubber regex, dedup heurístico
- Sem rede, sem DB, sem subprocess
- Tempo total < 5s

### Integration
- Marcar com `@pytest.mark.integration`
- Rodam contra stack docker compose subida
- Não rodam por padrão; CI/CD opt-in

### Fixtures
- Outputs reais de scanners (Nmap XML, ZAP JSON, Nuclei JSONL) em `tests/fixtures/<tool>_sample.<ext>`
- Adapters testam `normalize()` com fixtures sem precisar do binário

## Async

```python
import pytest

async def test_something() -> None:        # asyncio_mode = "auto" cuida do @pytest.mark.asyncio
    result = await some_async_func()
    assert result == expected
```

## Mocks

- DB: usar SQLite em memória (`sqlite+aiosqlite:///:memory:`) pra cobertura baixa-fricção
- HTTP externo: `respx` ou `httpx.MockTransport`
- LLM (litellm): mock `litellm.acompletion` retornando fixture
- subprocess: mock `asyncio.create_subprocess_exec` retornando bytes esperados

## Test data — alvos vulneráveis

- Para integration: profile `lab` no compose (Juice Shop, DVWA, WebGoat)
- Para unit: fixtures estáticas em `tests/fixtures/`

**Nunca** apontar testes pra hosts reais do banco ou pra qualquer alvo externo (mesmo CTF público) — usa lab local sempre.

## Cobertura mínima

- `domain/` (schemas, scrubber, dedup) — 90%+
- `adapters/` — 60%+ (`normalize` é o crítico)
- `api/` — 50%+ via TestClient
- `ai/` — 40%+ (mockar LLM)
- `jobs/` — 30%+ (worker é difícil testar isolado)

Não bloquear PR por cobertura, mas deixar visível.

## O que NÃO testar

- Renderização exata de HTML (testar dados, não markup)
- Latência de LLM (não-determinístico)
- Comportamento de scanners externos (responsabilidade deles)
- Chamadas reais a Anthropic/OpenAI/Shodan (só com mock)

## Convenção de nome

```python
def test_<unidade>_<comportamento>_<contexto>() -> None:
    # ex: test_scrubber_redacts_cpf_with_punctuation
    # ex: test_finding_dedup_keeps_higher_severity
    ...
```
