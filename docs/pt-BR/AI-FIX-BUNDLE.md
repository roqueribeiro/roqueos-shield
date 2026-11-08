# AI Fix Bundle

*Tradução de [AI-FIX-BUNDLE.md](../AI-FIX-BUNDLE.md), a versão principal, em inglês. Se as duas divergirem, vale a em inglês.*

> A especificação do contrato JSON que um agente de correção (Claude Code, Cursor, Copilot) lê para corrigir o que um scan achou. Para quem escreve esse agente, ou confere o que ele recebeu. Cada campo abaixo foi lido em `orchestrator/reporting/exporters/ai_bundle.py` e conferido contra um bundle gerado de um banco descartável; onde o código faz menos do que o nome do campo sugere, este documento diz.
>
> Como buscá-lo pela CLI, pela API e pelo MCP está em [INTEGRACOES.md](INTEGRACOES.md); o laço do agente que o usa, em [INTEGRACOES.md, seção 7](INTEGRACOES.md#7-o-laço-scan-patch-re-scan).

**Versão do schema:** `1.0.0` (`SCHEMA_VERSION` no exportador) · **Endpoint:** `GET /reports/{scan_id}/ai-bundle`

## Sumário

1. [Como obter o bundle](#1-como-obter-o-bundle)
2. [Garantias, e onde cada uma para](#2-garantias-e-onde-cada-uma-para)
3. [Estrutura de topo](#3-estrutura-de-topo)
4. [scan: o que rodou e o que não rodou](#4-scan-o-que-rodou-e-o-que-não-rodou)
5. [target e tech_stack_hints](#5-target-e-tech_stack_hints)
6. [summary e compliance](#6-summary-e-compliance)
7. [vulnerabilities](#7-vulnerabilities)
8. [patch_priority](#8-patch_priority)
9. [appendix](#9-appendix)
10. [Como um patcher deve consumir](#10-como-um-patcher-deve-consumir)
11. [Versionamento](#11-versionamento)

---

## 1. Como obter o bundle

| Caminho | Como |
| --- | --- |
| REST | `GET /reports/{scan_id}/ai-bundle`, qualquer credencial com `scans:read` (papel `viewer` para cima) |
| CLI | `roqueshield report <scan_id> --format bundle -o bundle.json` (`bundle` é o formato padrão) |
| MCP | a ferramenta `get_ai_bundle` |
| CLI de admin dentro do motor | `cai bundle <scan_id>` grava `reports/scan-<id>/ai-bundle.json` |

A rota responde `404 scan não encontrado` para id desconhecido e `500 falha ao gerar bundle: …` quando a montagem falha. Responde `200` para scan em **qualquer** estado, inclusive falho ou incompleto: a cobertura está dentro do bundle, em `scan`, e lê-la é trabalho de quem consome. A ferramenta MCP é mais dura: para scan falho, não terminado ou incompleto ela devolve `isError: true` com o motivo e o bundle como `bundle_parcial`.

## 2. Garantias, e onde cada uma para

**Ids estáveis.** `vulnerabilities[].id` é `uuid5(namespace fixo, deduped_key)`, e `instances[].instance_id` sai do mesmo jeito. O mesmo problema tem o mesmo id no scan de hoje e no de ontem, então quem consome consegue casar os dois. O que muda entre duas montagens do mesmo scan é o `generated_at`. A ordem de duas vulnerabilidades com o mesmo `patch_priority` segue a ordem das linhas no banco, que nenhuma consulta fixa; ordene por `id` você mesmo se precisar de ordem total.

**Deduplicado.** Antes de persistir, o pipeline junta os achados do mesmo scan com o mesmo `deduped_key`, ficando com o de maior severidade (`orchestrator/domain/dedup.py`). O bundle tem uma entrada por linha que sobrou, então na prática uma por problema.

**Evidência redigida.** Todo campo de `instances[].evidence` (`description`, `request_sent`, `response_received_excerpt`, `payload_used`, `snippet`) passa pelo `orchestrator/domain/scrubber.py` antes de ser servido. O scrubber troca CPF, CNPJ, número de cartão que passa no Luhn, CVV, e-mail, JWT, chave de acesso da AWS, cabeçalho `Authorization`, cabeçalhos `Cookie`/`Set-Cookie` e telefone brasileiro por marcadores como `<EMAIL>` e `<PAN:****1234>`.

Essa garantia tem dois limites, e os dois importam:

- **É uma lista de padrões, não um detector de segredo.** Token do GitHub, token do Slack ou senha em texto puro não estão na lista. Conferido aqui: `scrub("token = ghp_…")` devolve o token intacto. E os scanners de segredo põem o próprio trecho no snippet: o gitleaks guarda o campo `Match`, o trufflehog o campo `Raw`. Um bundle de scan de `repo` pode trazer uma credencial viva em `instances[].evidence.snippet`. Trate o bundle como sensível, como o repositório de onde ele veio.
- **Só a evidência é redigida.** `title`, `remediation.summary`, `remediation.rationale`, `ai_triage.*`, `instances[].location` e `target` saem como foram guardados.

**Ordenado.** `vulnerabilities` vem ordenado por `patch_priority`, 1 primeiro ([seção 8](#8-patch_priority)).

## 3. Estrutura de topo

```
{
  "schema_version": "1.0.0",
  "generated_at": "<ISO-8601, UTC>",
  "generator": { "tool": "cai", "version": "<versão do shield>", "model_used": "<modelo ou null>" },
  "scan":      { ... },   // seção 4
  "target":    { ... },   // seção 5
  "summary":   { ... },   // seção 6
  "compliance":{ ... },   // seção 6
  "vulnerabilities": [ ... ],   // seção 7
  "appendix":  { ... }    // seção 9
}
```

`generator.tool` é `cai`, o nome interno do motor. `generator.version` é a versão do shield (`orchestrator/__init__.py`, `0.5.1` hoje). `generator.model_used` é o modelo do primeiro achado que tem triagem de IA, ou `null` quando nenhum foi triado.

## 4. scan: o que rodou e o que não rodou

| Campo | Significado |
| --- | --- |
| `id`, `started_at`, `finished_at` | O scan; datas em ISO-8601 ou `null` |
| `scanners_requested` | O que o scan ia rodar |
| `scanners_executed` | O que rodou de fato. Não é o que foi pedido: scanner sem binário ou sem credencial não está aqui |
| `scanners_failed` | Nomes, em ordem, dos scanners que foram pulados |
| `scanners_failed_reason` | `{scanner: motivo}`, o motivo como o motor registrou |
| `coverage_complete` | `true` só quando algo rodou e nada foi pulado |
| `coverage_state` | `completa`, `incompleta` ou `desconhecida` |
| `coverage_note` | Uma frase para gente |

`desconhecida` quer dizer que o scan não registrou nem scanner executado nem pulado (linha anterior à migration 0007, scan ainda rodando, ou falha ao persistir). Nunca sai como completa. Os três valores de cobertura vêm de `orchestrator/reporting/coverage.py`, o único lugar que calcula cobertura para o bundle, o relatório executivo e a tela.

De um bundle gerado em que o trivy estava sem binário:

```json
"scanners_requested": ["semgrep", "gitleaks", "trivy"],
"scanners_executed": ["semgrep", "gitleaks"],
"scanners_failed": ["trivy"],
"scanners_failed_reason": {"trivy": "binário ausente"},
"coverage_complete": false,
"coverage_state": "incompleta",
"coverage_note": "COBERTURA INCOMPLETA: trivy não rodaram. Zero achados destes vetores NÃO significa alvo limpo."
```

**Zero vulnerabilidade só é limpo com `coverage_complete: true`.**

## 5. target e tech_stack_hints

| Campo | Significado |
| --- | --- |
| `primary_value` | O alvo escaneado (`unknown` se a linha do alvo sumiu) |
| `asset_type` | `url`, `domain`, `host`, `port`, `image`, `repo` ou `k8s_resource` |
| `label`, `contains_pii` | Como registrados no alvo |
| `scope` | `[primary_value]`. O bundle não traz a allowlist do shield |
| `out_of_scope` | Sempre `[]` hoje |
| `source_code_available_to_patcher` | `true` quando `asset_type` é `repo`: o patcher tem o código e pode corrigir em vez de só recomendar |
| `tech_stack_hints` | Abaixo |

`tech_stack_hints` é derivado das evidências que os scanners já produziram. É determinístico e não chama modelo:

| Campo | Origem |
| --- | --- |
| `languages` | Extensão do caminho do achado (`.py`, `.js`, `.ts`, `.java`, `.go`, e outras) |
| `package_managers` | Nome de manifesto no caminho (`requirements.txt`, `pyproject.toml`, `package.json`, `yarn.lock`, `go.mod`, `pom.xml`, `build.gradle`, `gemfile`, `composer.json`) |
| `runtimes` | `Dockerfile` ou `docker-compose.yml` no caminho |
| `servers` | Banner de serviço nos achados do nmap (nginx, apache, openssh, mysql, redis, e outros) |
| `source_repos`, `container_images` | O próprio alvo, quando é `repo` ou `image` |
| `frameworks` | Sempre `[]` hoje |
| `confidence` | `medium` quando houve algum sinal, `low` quando nenhum |

## 6. summary e compliance

`summary` conta o que está em `vulnerabilities`:

| Campo | Significado |
| --- | --- |
| `counts_by_severity` | `critical`, `high`, `medium`, `low`, `info`, sempre as cinco |
| `counts_by_category` | Contagem por `category` |
| `owasp_top10_2021` | Códigos distintos (`A03`), vindos da triagem de IA |
| `top_cwes` | Até cinco, o mais frequente primeiro |
| `patchable_automatically_count` | Entradas com `remediation.patch_strategy.confidence: high` |
| `needs_human_review_count` | O resto |

`compliance` é o mesmo mapeamento do `GET /reports/{id}/compliance`, refeito dos achados guardados:

| Campo | Significado |
| --- | --- |
| `risk_grade`, `risk_index`, `max_cvss` | Nota de postura de A a F, o índice por trás dela e o maior CVSS |
| `owasp_top10_2021`, `pci_dss_4_0`, `lgpd` | Cobertura por framework |
| `cwe_top25_2023` | CWEs do scan que estão no CWE Top 25 de 2023 |
| `findings_descartadas` | Quantos achados guardados não puderam ser lidos no schema atual |
| `nota_de_integridade` | `null`, ou uma frase dizendo que a nota acima deixou esses achados de fora e está otimista |

A nota de integridade existe porque `vulnerabilities` é montado das linhas cruas e inclui um achado que a nota, montada do schema validado, teve de largar. Leia `findings_descartadas` antes de confiar em `risk_grade`.

## 7. vulnerabilities

Um objeto por problema:

| Campo | Significado |
| --- | --- |
| `id` | `uuid5(deduped_key)`, estável entre scans |
| `deduped_key` | A identidade do problema, não da ocorrência |
| `title` | Como o scanner escreveu |
| `category` | Derivada do scanner, tabela abaixo |
| `severity` | Ajustada pela triagem de IA quando houve uma, senão a do scanner |
| `severity_original` | A que o scanner reportou |
| `confidence` | `tentative`, `firm` ou `certain` |
| `patch_priority` | 1 (urgente) a 5 ([seção 8](#8-patch_priority)) |
| `classification` | `owasp_top10_2021` (da triagem), `cwe` (lista), `cve` e `ghsa` (do id do achado quando começa com `CVE-` ou `GHSA`), `cvss_v3`, `epss_percentile` (sempre `null` hoje), `exploit_available` (sempre `false` hoje) |
| `discovered_by` | `tool`, `rule_id`, `rule_name` (o título), `raw_output_ref` |
| `instances[]` | Até 3, cada uma com `instance_id`, `location` e `evidence` redigida. Achado sem evidência ganha uma instância cuja evidência é a descrição redigida |
| `remediation` | Abaixo |
| `verification` | Abaixo |
| `ai_triage` | `rationale`, `is_likely_false_positive`, `business_impact`, `model_used`; `null` quando o achado não foi triado |

**Categoria e local por scanner.** O mapa é fixo no exportador:

| Scanner | `category` | `location.kind` | Campos em `location` | `patch_strategy.approach` |
| --- | --- | --- | --- | --- |
| zap, nuclei | `web` | `http_endpoint` | `url`, `method` (sempre `GET`), `host`, `parameter`, `parameter_location`, `request_template` (os três últimos `null`) | `code_change` |
| nmap, greenbone | `infra` | `host_port` | `host`, `port`, `protocol` | `config_change` |
| trivy | `deps` | `container_layer` | `image`, `package`, `version` | `dependency_upgrade` |
| gitleaks, trufflehog | `secret` | `repo_path` | `path`, `line` | `secret_rotation` |
| github_exposure, dnstwist, shodan, censys, subdomain_takeover | `osint` | `domain` | `domain` | `manual` |
| checkov | `misconfig` | `file_path` | `path`, `line` | `config_change` |
| kube_bench | `k8s` | `k8s_resource` | `resource_id` | `config_change` |
| qualquer outro | `infra` | `host_port` | `host`, `port`, `protocol` | `config_change` |

Dois limites neste mapa. **O semgrep não está nele**, então um achado de SAST sai como `infra` / `host_port` com o arquivo em `host` e a linha em `port` (visto num bundle gerado: `"host": "src/db.py", "port": "41"`), e com `config_change`, que ainda o conta como `patchable_automatically`. E `line` é sempre `null`: a linha, quando o scanner a dá, fica dentro de `path` (`src/app/config.py:12`). O patcher deve ler o caminho em vez de confiar em `line`.

**remediation:**

| Campo | Significado |
| --- | --- |
| `summary` | A remediação sugerida pela triagem, ou a do scanner, ou `""` |
| `rationale` | A justificativa da triagem, ou `""` |
| `patch_strategy` | `approach` (tabela acima); `confidence` `high` para `dependency_upgrade` e `config_change`, `medium` no resto; `estimated_effort` `small` para `config_change`, `medium` no resto; `blast_radius` `module` para `code_change`, `service` no resto |
| `code_search_patterns`, `before_after_examples` | Sempre `[]` hoje |
| `dependency_upgrade`, `config_change` | Sempre `null` hoje |
| `secret_rotation` | Para `secret_rotation`: `{credential_type: "unknown", scope: "unknown", rotation_steps: []}`; senão `null` |
| `references` | As referências do scanner |

Os valores de `patch_strategy` são uma regra fixa por categoria, não uma análise do achado.

**verification:** `method` é sempre `rerun_scanner`, com `rerun.scanner` (a ferramenta que achou), `rerun.scan_profile` (`focused`), `rerun.options.target` e `rerun.expected_outcome` (uma frase em inglês). `http_probe` é `null` e `suggested_unit_tests` é `[]`. Na prática, verificar é escanear de novo ([seção 10](#10-como-um-patcher-deve-consumir)).

## 8. patch_priority

```
base = posição da severidade + 1   # critical 1, high 2, medium 3, low 4, info 5
confiança tentative                → base + 1, no máximo 5
ai_triage.is_likely_false_positive → 5
```

A severidade usada é a ajustada. Achado que o modelo marcou como provável falso positivo vai para o fim da fila e **continua no bundle**: a marca é palpite do modelo, não veredito.

## 9. appendix

| Campo | Significado |
| --- | --- |
| `raw_scan_artifacts` | `[{tool, path}]` apontando para o relatório HTML do scan no disco do shield, ou `[]` quando não há. No máximo uma entrada |
| `scrubbing_applied` | `cpf`, `cnpj`, `pan_luhn`, `cvv`, `email`, `jwt`, `aws_keys`, `auth_header`, `phone_br`. O cabeçalho de cookie também é redigido, embora não esteja nesta lista |
| `patcher_instructions` | Uma frase fixa em inglês. Ela cita `code_search_patterns` e `before_after_examples`, que hoje vêm vazios |

## 10. Como um patcher deve consumir

1. Confira `scan.coverage_complete`. Se for `false`, o que falta está em `scan.scanners_failed_reason`; não declare o alvo limpo.
2. Percorra `vulnerabilities` na ordem de `patch_priority`.
3. Use `target.tech_stack_hints` para linguagem e gerenciador de pacote, e `target.source_code_available_to_patcher` para decidir entre corrigir e recomendar.
4. Para cada entrada, leia `instances[].location` e `remediation`, e proponha o patch. Para SAST, tire arquivo e linha do local como descrito na [seção 7](#7-vulnerabilities).
5. Trate `ai_triage.is_likely_false_positive: true` como candidato a descarte, não como verdade.
6. Confirme escaneando o mesmo alvo de novo e comparando por `deduped_key`, com o `coverage_complete` do scan novo ainda `true`. Registre o resultado com `POST /findings/resolve`; o status mora no shield, não no bundle.

Nunca cole um bundle em issue pública, chat ou log: a [seção 2](#2-garantias-e-onde-cada-uma-para) explica por que ele pode trazer uma credencial.

## 11. Versionamento

Mudança que **quebra** o contrato (remover campo, mudar tipo ou significado) sobe a major de `schema_version`. Campo novo e opcional sobe a minor. Os campos que hoje são valor fixo (`out_of_scope`, `frameworks`, `epss_percentile`, `exploit_available`, `code_search_patterns`, `before_after_examples`, `dependency_upgrade`, `config_change`, `http_probe`, `suggested_unit_tests`) podem passar a trazer dado sem subir a major, porque o tipo deles não muda.

## Quando algo não funciona

- `404 scan não encontrado`: o id está errado, ou o scan foi apagado (`DELETE /scans/{id}` remove os achados dele; a trilha de auditoria guarda o registro).
- `500 falha ao gerar bundle`: leia o log do shield (`roqueshield logs orchestrator`). [QUANDO-QUEBRA.md](QUANDO-QUEBRA.md) cobre as causas comuns.
- O bundle tem zero vulnerabilidade: olhe `scan.coverage_state` antes de acreditar.
- `compliance.findings_descartadas` acima de zero: alguns achados guardados não validam mais no schema atual (típico depois de um rollback ou com duas versões de worker durante uma atualização). As vulnerabilidades estão listadas; a nota é que não as conta.
