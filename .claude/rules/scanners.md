---
description: Convenções para criar/manter ScannerAdapters em orchestrator/adapters/
paths:
  - "orchestrator/adapters/**"
  - "tests/unit/test_*adapter*"
---

# Convenções de ScannerAdapter

Todo adapter implementa o `ScannerAdapter` Protocol em `orchestrator/adapters/base.py`. **Não criar variantes**: se o lifecycle não bate, o adapter está modelado errado.

Este arquivo é lido junto com [60-contrato-do-silencio.md](60-contrato-do-silencio.md), que manda em tudo abaixo. O template completo de adapter está na skill [`cai-add-adapter`](../skills/cai-add-adapter/SKILL.md), seção 3; o gate `scripts/check_no_silence.py` roda sobre os blocos de código deste arquivo, da skill e do agent `adapter-author` (`tests/unit/test_w3_templates_adapter.py`).

## Lifecycle obrigatório

```python
class XyzAdapter:
    name = "xyz"  # ID curto, lowercase, sem espaço

    async def health(self) -> bool: ...
    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle: ...
    async def poll(self, handle: ScanHandle) -> ScanStatus: ...
    async def fetch_results(self, handle: ScanHandle) -> RawResults: ...
    async def normalize(self, raw: RawResults) -> list[Finding]: ...
```

- `health()` SEMPRE retorna `bool`. Nunca lança (captura `OSError` e devolve False). Para API, round-trip de verdade: construir o cliente do SDK não prova a credencial.
- `start_scan()` é **não-bloqueante**. Subprocess: a task, guardada em `self._tasks[native_id]`, devolve `(returncode, caminho_do_report)`. Asset type incompatível levanta `ScanIntegrityError`.
- `poll()` retorna `RUNNING/DONE/FAILED/CANCELED` e **lê o returncode**: `task.done()` diz que terminou, não que deu certo. Nunca bloqueia.
- `fetch_results()` só é chamado quando `poll() == DONE`. Report ausente ou ilegível levanta `ScanIntegrityError`; cobertura parcial vai em `coverage_gaps`.
- `normalize()` retorna `list[Finding]`. Item sem os campos mínimos é contado e declarado em `raw.coverage_gaps`; saída que não parseia inteira é `ScanIntegrityError`. Nunca "lista vazia + log": log ninguém lê.

## Os três níveis

| Situação | O que fazer | Onde aparece para o usuário |
| --- | --- | --- |
| Rodou e não achou | devolver `[]` | achado nenhum, cobertura completa |
| Não deu para verificar | `raise ScanIntegrityError` | `scanners_skipped`, `coverage_complete: false` |
| Verificou em parte | preencher `RawResults.coverage_gaps` | achado **INFO** no relatório |

`poll` e `fetch_results` de um adapter de subprocess, na forma que o gate aceita:

```python
    async def poll(self, handle: ScanHandle) -> ScanStatus:
        task = self._tasks.get(handle.native_id)
        if task is None:
            return ScanStatus.FAILED
        if not task.done():
            return ScanStatus.RUNNING
        rc, _ = task.result()
        return ScanStatus.DONE if rc == 0 else ScanStatus.FAILED

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        task = self._tasks.get(handle.native_id)
        if task is None or not task.done():
            raise ScanIntegrityError(f"{self.name}: fetch_results sem execução concluída")
        rc, out = task.result()
        if not out.exists():
            raise ScanIntegrityError(f"{self.name} saiu com rc={rc} e não escreveu o report")
        gaps: list[str] = []
        itens = read_jsonl(out, adapter=self.name, gaps=gaps)
        return RawResults(adapter=self.name, payload=itens, coverage_gaps=gaps)
```

Proibido, e o gate reprova: `except` que termina em `return []`, `return {}`, `return RawResults(payload={})`, `pass` ou `continue` sem `raise` nem registro de lacuna; `except json.JSONDecodeError: continue` (use `read_jsonl`); dicionário de sucesso fabricado dentro de `except`; `poll` decidindo só por `task.done()`. O vazio que é mesmo o certo leva `# silencio-ok: motivo` na linha do `except`.

## Schema de saída: Finding canônico

Todos os adapters produzem `orchestrator.domain.schemas.Finding`. **Não inventar campos**.

Campos obrigatórios:
- `scan_id`: placeholder UUID; o pipeline reescreve
- `target`: Pydantic `Target` com `asset_type` e `value`
- `source_tool`: igual a `self.name`
- `title`: uma linha, descritiva
- `description`: pode ser longo; truncar evidências enormes a ~2000 chars
- `severity`: heurística do scanner; a IA ajusta depois em `ai_triage.adjusted_severity`

Campos quase-sempre úteis:
- `source_rule_id`: ID nativo do scanner (plugin id ZAP, template id Nuclei, OID Greenbone)
- `vuln_id`: CVE quando houver
- `cwe[]`: lista de CWEs
- `confidence`: `tentative/firm/certain` baseado em quão certeira é a detecção
- `evidence[]`: `Evidence(description=, snippet=, request=, response=, payload=)`
- `remediation`: texto se o scanner fornecer

**Nunca** sobrescrever `severity` com base em contexto do alvo (PII/PCI). Isso é trabalho do `AIAnalyzer`. O scanner só reporta o que viu.

## Subprocess vs HTTP API

- **Binário CLI** (nmap, nuclei, gitleaks, trufflehog, dnstwist, checkov, kube-bench, trivy CLI, semgrep):
  - `asyncio.create_subprocess_exec` com argv list (não shell)
  - `tempfile.mkdtemp(prefix="cai-<adapter>-")` pra outputs (o worker tem raiz só de leitura; `/tmp` e o HOME são tmpfs)
  - task em `self._tasks[native_id]` devolvendo `(rc, path)`
  - egress fechado por padrão: a flag que desliga update e telemetria (`-duc`, `-ni`, `--no-update`, `--metrics off`) vai sempre
  - cascata (etapa que lê o arquivo da anterior) checa cada etapa; `if arquivo.exists()` não basta
- **HTTP API** (zap, trivy server, github, shodan, censys):
  - `httpx.AsyncClient` com `base_url` e `timeout`
  - Implementar `aclose()` pra cleanup
  - Erro HTTP, cota estourada, chave inválida e rate limit levantam `ScanIntegrityError` ou viram `coverage_gaps` (o que foi verificado antes do limite fica, o resto é lacuna). Nunca `break` calado
  - Paginação é cobertura: compare o que leu com o total reportado
  - Não vazar API key em logs nem em argv

## Testes

Todo adapter novo precisa de:
1. Unit test mockando o backend (sem rede real)
2. Fixture XML/JSON real em `tests/fixtures/<adapter>_sample.<ext>`
3. Teste de `normalize(raw)` com a fixture validando ≥1 Finding
4. Teste do lado da falha (report ausente, rc de erro, saída ilegível levantam `ScanIntegrityError`), com teste de mutação: revertido o conserto, ele reprova

Padrão de nome: `tests/unit/test_<adapter>_adapter.py`. O lado da falha também entra em `tests/unit/test_silencio_adapters.py`.

## Adicionando ao pipeline

Adapter novo NÃO é automaticamente chamado pelo `run_scan()`. Para integrar:

1. Fábrica em `_build_adapters` e asset types em `_SCANNER_ASSET_SUPPORT` (`orchestrator/jobs/pipelines.py`); OSINT em `orchestrator/jobs/exposure.py`
2. Documentar no `README.md` (tabela de adapters) e em `docs/ARCHITECTURE.md` com o par em `docs/pt-BR/` (o gate de docs reprova adapter construível sem doc)
3. Binário na imagem do orchestrator (`docker/images/orchestrator/Dockerfile`), com pin e `--version` no build: é nela que o `cai-worker` roda os scanners
4. Permissions no `.claude/settings.json` se o adapter rodar binário novo

## Severity heurística

Quando o scanner não fornece severity nativo (Nmap, kube-bench scored), use:
- Banner/info sem exploração direta: `info` ou `low`
- Serviço inseguro exposto (telnet, ftp, smb): `high`
- Serviço comum em porta padrão (22, 80, 443): `info`
- Falha CIS K8s scored: `medium`; not scored: `low`

Sempre justificar a heurística em comentário no código.
