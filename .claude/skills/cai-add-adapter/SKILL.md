---
name: cai-add-adapter
description: Adiciona um novo ScannerAdapter ao projeto. Use quando usuário pede "criar adapter pra X", "integrar a ferramenta Y", "adicionar suporte a Z scanner". Gera código seguindo o ScannerAdapter Protocol e o contrato do silêncio, e atualiza pipeline, imagem e documentação.
when_to_use: integração de novo scanner, criação de adapter, expansão da plataforma
argument-hint: "<adapter-name> <tool-binary-or-api>"
allowed-tools: Read Edit Write Glob Grep
---

# Skill: Adicionar novo ScannerAdapter

Use este skill quando o usuário quer integrar uma nova ferramenta de scan. O processo segue ordem rígida: não pular etapas.

A pergunta que governa o adapter inteiro vem de [`.claude/rules/60-contrato-do-silencio.md`](../../rules/60-contrato-do-silencio.md):

> **Zero achados aqui significa *limpo*, ou significa *não rodou*? Se não houver como distinguir, falta um sinal.**

| Situação | O que o adapter faz | Onde aparece |
| --- | --- | --- |
| Rodou e não achou | devolve `[]` | nenhum achado, cobertura completa |
| Não deu para verificar | `raise ScanIntegrityError` | `scanners_skipped`, `coverage_complete: false` |
| Verificou em parte | preenche `RawResults.coverage_gaps` | achado INFO no relatório |

## 1. Coletar requisitos

Pergunte ao usuário (em uma única mensagem):

1. **Nome** do adapter (snake_case): `xyz`, arquivo `xyz_adapter.py`
2. **Tipo de integração**: subprocess (CLI) ou HTTP API?
3. **Saída**: JSON, XML, JSONL? Como o scanner diz que **falhou** (returncode, campo de erro, contagem de regras carregadas)?
4. **Rede**: o scanner tenta a internet sozinho (update, telemetria, templates)? Qual flag desliga?
5. **Asset types** aceitos (host, url, repo, image, domain, k8s_resource)

## 2. Estudar adapter existente similar

Antes de escrever, leia o adapter mais próximo:

- **Subprocess CLI com JSONL**: [orchestrator/adapters/trufflehog_adapter.py](../../../orchestrator/adapters/trufflehog_adapter.py) e [nuclei_adapter.py](../../../orchestrator/adapters/nuclei_adapter.py)
- **Subprocess CLI com XML**: [orchestrator/adapters/nmap_adapter.py](../../../orchestrator/adapters/nmap_adapter.py)
- **HTTP API com lifecycle longo e paginação**: [orchestrator/adapters/zap_adapter.py](../../../orchestrator/adapters/zap_adapter.py)
- **HTTP API síncrona com rate limit**: [orchestrator/adapters/github_exposure_adapter.py](../../../orchestrator/adapters/github_exposure_adapter.py)
- **Clone + scan**: [orchestrator/adapters/gitleaks_adapter.py](../../../orchestrator/adapters/gitleaks_adapter.py)

Ler `orchestrator/adapters/base.py`: o Protocol, `ScanIntegrityError`, `read_jsonl` e `coverage_gap_finding`.

## 3. Criar o adapter

Path: `orchestrator/adapters/<name>_adapter.py`. Template (subprocess com saída JSONL); troque `xyz`/`Xyz` pelo nome real:

```python
"""Xyz adapter: <o que ele verifica, em uma linha>."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from orchestrator.adapters.base import ScanIntegrityError, read_jsonl
from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Evidence,
    Finding,
    RawResults,
    ScanHandle,
    ScanStatus,
    Severity,
    Target,
)

log = structlog.get_logger(__name__)

_XYZ_SEVERITY: dict[str, Severity] = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFO,
}
_ACEITA = {AssetType.URL, AssetType.HOST}


class XyzAdapter:
    name = "xyz"

    def __init__(self, bin_path: str | None = None) -> None:
        self.bin = bin_path or shutil.which("xyz") or "xyz"
        # A task devolve (returncode, caminho do report): o poll lê o rc.
        self._tasks: dict[str, asyncio.Task[tuple[int, Path]]] = {}
        self._outs: dict[str, Path] = {}
        self._stderr: dict[str, str] = {}

    async def health(self) -> bool:
        # O único método isento do gate. Para API, faça um round-trip de verdade
        # (construir o cliente do SDK não prova a credencial).
        try:
            p = await asyncio.create_subprocess_exec(
                self.bin,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await p.communicate()
            return p.returncode == 0
        except OSError:
            return False

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        if target.asset_type not in _ACEITA:
            # Alvo incompatível não é alvo limpo: vira scanners_skipped.
            raise ScanIntegrityError(
                f"xyz não verifica asset_type {target.asset_type.value}"
            )
        out = Path(tempfile.mkdtemp(prefix="cai-xyz-")) / "out.jsonl"
        # Egress fechado por padrão: a flag que desliga update e telemetria vai
        # sempre. Sem ela o scanner pendura até o timeout numa rede de banco.
        cmd = [self.bin, "-target", target.value, "-jsonl", "-o", str(out), "-no-update"]
        native_id = str(uuid4())

        async def _run() -> tuple[int, Path]:
            p = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err = await p.communicate()
            self._stderr[native_id] = err.decode(errors="replace")[-2000:]
            return (p.returncode if p.returncode is not None else -1, out)

        self._outs[native_id] = out
        self._tasks[native_id] = asyncio.create_task(_run())
        log.info("xyz.start_scan", cmd=cmd)
        return ScanHandle(
            adapter=self.name, native_id=native_id, metadata={"out": str(out)}
        )

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        task = self._tasks.get(handle.native_id)
        if task is None:
            return ScanStatus.FAILED
        if not task.done():
            return ScanStatus.RUNNING
        # task.done() diz que o processo terminou, não que deu certo.
        rc, _ = task.result()
        # Confira na ferramenta real o que cada rc significa (há scanner que sai 1
        # quando ACHA algo). O que não for sucesso conhecido é FAILED.
        return ScanStatus.DONE if rc == 0 else ScanStatus.FAILED

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        task = self._tasks.get(handle.native_id)
        if task is None or not task.done():
            raise ScanIntegrityError("xyz: fetch_results sem execução concluída")
        rc, out = task.result()
        if not out.exists():
            # Report ausente não é "nada encontrado".
            raise ScanIntegrityError(
                f"xyz saiu com rc={rc} e não escreveu o report: "
                f"{self._stderr.get(handle.native_id, '')[-300:]}"
            )
        gaps: list[str] = []
        # read_jsonl: tudo ilegível levanta ScanIntegrityError; parte ilegível
        # preserva as linhas boas e declara a lacuna em `gaps`.
        itens = read_jsonl(out, adapter=self.name, gaps=gaps)
        # Se o scanner informa quanto verificou (regras carregadas, páginas, alvos),
        # compare com o esperado aqui: zero regras é ScanIntegrityError, primeira
        # página de N é lacuna em `gaps`.
        return RawResults(adapter=self.name, payload=itens, coverage_gaps=gaps)

    async def normalize(self, raw: RawResults) -> list[Finding]:
        findings: list[Finding] = []
        placeholder = uuid4()  # o pipeline reescreve o scan_id
        descartados = 0
        for item in raw.payload:
            regra = item.get("rule_id")
            if not regra:
                descartados += 1
                continue
            sev_nativa = str(item.get("severity", "")).lower()
            findings.append(
                Finding(
                    scan_id=placeholder,
                    target=Target(asset_type=AssetType.URL, value=item.get("url", "")),
                    source_tool=self.name,
                    source_rule_id=regra,
                    title=item.get("title") or regra,
                    description=(item.get("description") or "")[:2000],
                    # Severidade do scanner; o contexto do alvo é da triagem de IA.
                    severity=_XYZ_SEVERITY.get(sev_nativa, Severity.INFO),
                    confidence=Confidence.FIRM,
                    evidence=[
                        Evidence(
                            description="saída do xyz",
                            snippet=str(item.get("matched", ""))[:2000],
                        )
                    ],
                )
            )
        if descartados:
            # Item sem os campos mínimos não some calado: vira lacuna declarada.
            raw.coverage_gaps.append(
                f"{descartados} item(ns) da saída do xyz sem rule_id foram descartados"
            )
        return findings

    async def cleanup(self, handle: ScanHandle) -> None:
        from orchestrator.adapters._cleanup import cleanup_subprocess_handle

        await cleanup_subprocess_handle(
            native_id=handle.native_id,
            tasks=self._tasks,  # type: ignore[arg-type]
            output_paths=self._outs,
            adapter_name=self.name,
        )
```

Regras que o template aplica, todas da regra 60:

- **Leia o returncode.** A task devolve `(rc, path)` e o `poll` lê `rc`.
- **`read_jsonl`**, nunca `except json.JSONDecodeError: continue`.
- **Nunca fabrique payload de sucesso** dentro de um `except` (nada de `{"matches": [], "total": 0}`).
- **Nenhum `except` termina em vazio** (`return []`, `pass`, `continue`) sem `raise` ou registro em `gaps`/`coverage_gaps`. O vazio que é mesmo o certo leva `# silencio-ok: motivo` na linha do `except`.
- **Cascata checa cada etapa**: `if arquivo_anterior.exists()` faz a primeira falha apagar as seguintes em silêncio.
- **Paginação é cobertura**: primeira página devolvida como total é lacuna.
- **Egress fechado por padrão** (`-duc`, `-ni`, `--no-update`, `--metrics off`).

Para HTTP API, o mesmo vale: status HTTP de erro, cota estourada e chave inválida levantam `ScanIntegrityError`; resposta parcial vira `coverage_gaps`.

## 4. Adicionar fixture e testes

- `tests/fixtures/<name>_sample.<ext>`: output real do scanner contra alvo do lab.
- `tests/unit/test_<name>_adapter.py`, com os **dois lados**:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.adapters.base import ScanIntegrityError
from orchestrator.adapters.xyz_adapter import XyzAdapter
from orchestrator.domain.schemas import RawResults

FIXTURE = Path(__file__).parent.parent / "fixtures" / "xyz_sample.jsonl"


async def test_xyz_normalize_produz_findings() -> None:
    itens = [json.loads(linha) for linha in FIXTURE.read_text().splitlines() if linha]
    findings = await XyzAdapter().normalize(RawResults(adapter="xyz", payload=itens))
    assert findings
    assert all(f.source_tool == "xyz" for f in findings)


async def test_xyz_report_ausente_nao_vira_alvo_limpo(tmp_path: Path) -> None:
    # Mutação: troque o raise do fetch_results por `return RawResults(payload=[])`
    # e este teste tem que reprovar.
    ...
    with pytest.raises(ScanIntegrityError):
        ...
```

O segundo teste entra também em `tests/unit/test_silencio_adapters.py` (a ferramenta não mente quando falha), e o adapter ganha um caso em `tests/integration/test_efetividade_e2e.py` se ele cobre uma camada nova (a ferramenta acha de verdade).

## 5. Integrar no pipeline

- `orchestrator/jobs/pipelines.py`: a fábrica em `_build_adapters` e os asset types em `_SCANNER_ASSET_SUPPORT`. Adapter fora da fábrica é órfão: pedir por ele vira `scanner.unknown`.
- OSINT: `orchestrator/jobs/exposure.py`.

## 6. Atualizar infra

- **Imagem do orchestrator** ([docker/images/orchestrator/Dockerfile](../../../docker/images/orchestrator/Dockerfile)): é nela que o `cai-worker` roda os scanners como subprocesso. Pin de versão, binário conferido no build (`--version`) e dados offline (regras, templates) embarcados com piso validado. O `kali-toolbox` não é onde o scan roda.
- **Raiz só de leitura**: o worker sobe com `read_only: true`. O scanner escreve só em `/tmp`, no HOME (tmpfs) ou em `/app/data`; caminho novo de escrita pede um tmpfs no `docker/compose.yml`.
- **`pyproject.toml`** + `uv lock`: dependências Python novas.
- **`orchestrator/config.py`** + **`.env.example`**: variáveis novas (o gate de docs reprova `Settings` fora do `.env.example`).

## 7. Documentar (no mesmo commit, regra 50)

- `README.md`: linha na tabela de adapters (o gate de docs reprova adapter construível sem documentação).
- `docs/ARCHITECTURE.md` e `docs/pt-BR/ARQUITETURA.md`: tabela de adapters.
- `.claude/skills/cai-scan/SKILL.md`: mencionar o novo adapter como opção.

## 8. Validar

```bash
make test ARGS=tests/unit/test_<name>_adapter.py
python scripts/check_no_silence.py
python scripts/check_docs_fresh.py
make build
make smoke  # depois inspecionar reports/ pra confirmar findings do novo adapter
```

## Checklist final

- [ ] `health()` retorna bool, não lança, e faz round-trip quando é API
- [ ] `start_scan` é não-bloqueante e rejeita asset type incompatível com `ScanIntegrityError`
- [ ] `poll` lê `task.result()` (rc), não só `task.done()`
- [ ] `fetch_results` levanta quando não dá para verificar e usa `read_jsonl` para JSONL
- [ ] cobertura parcial vai em `coverage_gaps`, não em log
- [ ] `normalize` produz `Finding` canônico, sem campos extras; severidade é a do scanner
- [ ] teste de mutação: reverter o `raise` faz um teste reprovar
- [ ] `check_no_silence.py` e `check_docs_fresh.py` com exit 0
- [ ] pipeline, imagem, README e ARCHITECTURE (com o par) atualizados
