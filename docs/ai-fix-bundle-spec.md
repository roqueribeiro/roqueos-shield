# AI Fix Bundle — especificação do contrato

**Schema version:** `1.0.0` · endpoint: `GET /reports/{scan_id}/ai-bundle`

O Fix Bundle é o entregável que fecha a ponta "scan → fix": um JSON determinístico
que outra IA (Claude Code, Cursor, Copilot) consome para propor patches. Ele existia
como código com `SCHEMA_VERSION = "1.0.0"` e duas docstrings apontando para este
arquivo — que não estava no repo. Um contrato versionado sem contrato escrito é fé no
formato implícito; este documento é o contrato.

## Garantias

- **Determinístico.** Mesmo `scan_id` produz o mesmo bundle (a menos de timestamps).
  `vulnerabilities[].id` é `uuid5(namespace, deduped_key)` — estável entre execuções,
  então o consumidor pode casar um finding de hoje com o mesmo de ontem.
- **Deduplicado.** Uma entrada por problema (`deduped_key`), não por ocorrência.
- **Scrubbed.** Todo texto livre (descrição, evidência, snippet) passa pelo scrubber
  de PII/PCI antes de ser servido. Credencial não sai no entregável.
- **Priorizado.** A lista vem ordenada por `patch_priority` (1 = urgente).

## Estrutura

```
{
  "schema_version": "1.0.0",
  "generated_at": "<ISO-8601>",
  "generator": { "tool": "cai-orchestrator", "model_used": "<modelo da triagem>" },
  "scan": { "id", "started_at", "finished_at", "scanners_executed", "scanners_failed" },
  "target": {
    "primary_value", "asset_type", "label", "scope", "out_of_scope", "contains_pii",
    "tech_stack_hints": { ... },
    "source_code_available_to_patcher": <bool>
  },
  "summary": { "counts_by_severity", ... },
  "compliance": { "risk_grade", "frameworks", ... },
  "vulnerabilities": [ { ... } ],
  "appendix": { "raw_scan_artifacts": [...] }
}
```

### `target.tech_stack_hints`

Derivado das evidências que os scanners já produziram — determinístico, sem LLM:
caminho de arquivo dá linguagem e gerenciador de pacote, banner de serviço (nmap) dá
servidor, o alvo dá repositório ou imagem.

| campo | origem |
| --- | --- |
| `languages` | extensão do arquivo nos findings (semgrep, gitleaks, trivy, checkov) |
| `package_managers` | manifesto encontrado (`requirements.txt`, `package.json`, `go.mod`, …) |
| `runtimes` | `Dockerfile` / `docker-compose.yml` nos findings |
| `servers` | banner de serviço do nmap (nginx, apache, openssh, mysql, …) |
| `source_repos` / `container_images` | alvo do scan quando REPO / IMAGE |
| `confidence` | `medium` quando houve sinal, `low` quando nada foi derivado |

`source_code_available_to_patcher` é `true` quando o alvo é um REPO — o patcher tem o
código à mão, então pode aplicar patch em vez de só recomendar.

### `vulnerabilities[]`

| campo | significado |
| --- | --- |
| `id` | `uuid5(deduped_key)` — estável entre scans |
| `deduped_key` | chave do problema (não da ocorrência) |
| `title`, `category` | `web` / `infra` / `deps` / `secret` / `code` / `osint` |
| `severity` | **severidade ajustada pela IA** (a triagem sobrescreve a do scanner) |
| `severity_original` | a que o scanner reportou, preservada |
| `confidence` | `tentative` / `firm` / `certain` |
| `patch_priority` | 1 = urgente … 5 = por último. Combina severidade, confiança e triagem: um finding marcado como **provável falso positivo vai para 5**, sem sumir do bundle |
| `classification` | OWASP Top 10 2021, CWE, CVE/GHSA, CVSS v3 |
| `instances[]` | `location` + `evidence` (já scrubbed), no máximo 3 |
| `remediation` | abordagem + passos |
| `verification` | como confirmar que o patch resolveu |
| `ai_triage` | `rationale`, `is_likely_false_positive`, `business_impact`, `model_used` |

## Como um patcher deve consumir

1. Percorrer `vulnerabilities` na ordem de `patch_priority`.
2. Usar `target.tech_stack_hints` para saber linguagem, gerenciador e onde procurar.
3. Para cada item, ler `instances[].location` e `remediation`, propor o patch.
4. Tratar `ai_triage.is_likely_false_positive = true` como candidato a descarte, não
   como verdade: é palpite do modelo, não veredito.
5. Confirmar com `verification`, e re-escanear o mesmo alvo para comparar por
   `deduped_key` (o status sobrevive ao re-scan via `finding_status`).

## Compatibilidade

Mudança que **quebra** o contrato (remover campo, mudar tipo ou semântica) sobe a
major de `schema_version`. Campo novo, opcional, sobe a minor. O RoqueShield consome
este bundle pela rota proxiada `/pentest/api/reports/{scan_id}/ai-bundle`.
