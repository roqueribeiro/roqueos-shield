# AI Fix Bundle

*Also available in [Brazilian Portuguese](pt-BR/AI-FIX-BUNDLE.md).*

> The specification of the JSON contract that a patching agent (Claude Code, Cursor, Copilot) reads to fix what a scan found. For whoever writes that agent, or checks what it received. Every field below was read from `orchestrator/reporting/exporters/ai_bundle.py` and checked against a bundle generated from a scratch database; where the code does less than the field name suggests, this document says so.
>
> How to fetch it from the CLI, the API and MCP is in [INTEGRATIONS.md](INTEGRATIONS.md); the agent loop that uses it, in [INTEGRATIONS.md, section 7](INTEGRATIONS.md#7-the-loop-scan-patch-re-scan).

**Schema version:** `1.0.0` (`SCHEMA_VERSION` in the exporter) · **Endpoint:** `GET /reports/{scan_id}/ai-bundle`

## Table of contents

1. [Getting the bundle](#1-getting-the-bundle)
2. [Guarantees, and where each one stops](#2-guarantees-and-where-each-one-stops)
3. [Top-level structure](#3-top-level-structure)
4. [scan: what ran and what did not](#4-scan-what-ran-and-what-did-not)
5. [target and tech_stack_hints](#5-target-and-tech_stack_hints)
6. [summary and compliance](#6-summary-and-compliance)
7. [vulnerabilities](#7-vulnerabilities)
8. [patch_priority](#8-patch_priority)
9. [appendix](#9-appendix)
10. [How a patcher should consume it](#10-how-a-patcher-should-consume-it)
11. [Versioning](#11-versioning)

---

## 1. Getting the bundle

| Path | How |
| --- | --- |
| REST | `GET /reports/{scan_id}/ai-bundle`, any credential with `scans:read` (role `viewer` and up) |
| CLI | `roqueshield report <scan_id> --format bundle -o bundle.json` (`bundle` is the default format) |
| MCP | the `get_ai_bundle` tool |
| Admin CLI inside the engine | `cai bundle <scan_id>` writes `reports/scan-<id>/ai-bundle.json` |

The route answers `404 scan não encontrado` ("scan not found") for an unknown id and `500 falha ao gerar bundle: …` ("failed to build bundle") when building fails. It answers `200` for a scan in **any** state, including failed or incomplete: the coverage is inside the bundle, in `scan`, and reading it is the consumer's job. The MCP tool is stricter: for a failed, unfinished or incomplete scan it returns `isError: true` with the reason and the bundle as `bundle_parcial`.

## 2. Guarantees, and where each one stops

**Stable ids.** `vulnerabilities[].id` is `uuid5(fixed namespace, deduped_key)`, and `instances[].instance_id` is derived the same way. The same problem gets the same id in today's scan and yesterday's, so a consumer can match them. What changes between two builds of the same scan is `generated_at`. The order of two vulnerabilities with the same `patch_priority` follows the database row order, which no query fixes; sort by `id` yourself if you need a total order.

**Deduplicated.** Before persisting, the pipeline merges findings of the same scan with the same `deduped_key`, keeping the one with the highest severity (`orchestrator/domain/dedup.py`). The bundle has one entry per remaining row, so in practice one per problem.

**Scrubbed text.** Every field of `instances[].evidence` (`description`, `request_sent`, `response_received_excerpt`, `payload_used`, `snippet`), plus `title`, `discovered_by.rule_name`, `remediation.summary`, `remediation.rationale`, `ai_triage.rationale` and `ai_triage.business_impact`, goes through `orchestrator/domain/scrubber.py` before it is served. The scrubber replaces CPF, CNPJ, card numbers that pass Luhn, CVV, e-mail, JWT, AWS access keys, GitHub tokens (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`), Slack tokens (`xoxa-`, `xoxb-`, `xoxp-`, `xoxr-`, `xoxs-`), the value of a password or secret assignment (`password=`, `passwd:`, `secret:`, `api_key=`, `client_secret` and similar), `Authorization` headers, `Cookie`/`Set-Cookie` headers and Brazilian phone numbers with placeholders such as `<EMAIL>`, `<GITHUB_TOKEN>`, `<REDACTED_SECRET>` and `<PAN:****1234>`.

**Secret scanners do not carry the secret.** gitleaks runs with `--redact`, so its report already has `REDACTED` in `Secret` and `Match`; if a report still has the secret in clear (an old version, or a report made without the flag), the adapter replaces it inside `Match` before it becomes evidence, and drops `Match` when it cannot tell where the secret is. trufflehog evidence comes from its `Redacted` field, never from `Raw`; when `Redacted` is empty the snippet says the value was omitted. The deduplication discriminator, when it falls back to the secret, stores a SHA-256 prefix of it, not the value.

This guarantee has two limits, and both matter:

- **It is a list of patterns, not a secret detector.** A credential with a format that is not on the list, written without a key name such as `password` or `secret` next to it, passes unchanged (a bare random string in a config file, a private key block). The secret scanners no longer put the secret in the snippet, but other scanners can still quote one. Treat the bundle as sensitive, like the repository it came from.
- **Location and target are served as stored.** `instances[].location` and `target` are not scrubbed, because the patcher needs the real path and URL. A URL that carries a token in its query string reaches the bundle as it is.

**Ordered.** `vulnerabilities` comes sorted by `patch_priority`, 1 first ([section 8](#8-patch_priority)).

## 3. Top-level structure

```
{
  "schema_version": "1.0.0",
  "generated_at": "<ISO-8601, UTC>",
  "generator": { "tool": "cai", "version": "<shield version>", "model_used": "<model or null>" },
  "scan":      { ... },   // section 4
  "target":    { ... },   // section 5
  "summary":   { ... },   // section 6
  "compliance":{ ... },   // section 6
  "vulnerabilities": [ ... ],   // section 7
  "appendix":  { ... }    // section 9
}
```

`generator.tool` is `cai`, the engine's internal name. `generator.version` is the shield's version (`orchestrator/__init__.py`, `0.5.1` today). `generator.model_used` is the model of the first finding that has an AI triage, or `null` when none was triaged.

## 4. scan: what ran and what did not

| Field | Meaning |
| --- | --- |
| `id`, `started_at`, `finished_at` | The scan; dates in ISO-8601 or `null` |
| `scanners_requested` | What the scan was going to run |
| `scanners_executed` | What actually ran. Not what was requested: a scanner with no binary or no credential is not here |
| `scanners_failed` | Sorted names of the scanners that were skipped |
| `scanners_failed_reason` | `{scanner: reason}`, the reason in Portuguese as the engine recorded it |
| `coverage_complete` | `true` only when something ran and nothing was skipped |
| `coverage_state` | `completa`, `incompleta` or `desconhecida` (complete, incomplete, unknown) |
| `coverage_note` | One sentence for a human, in Portuguese |

`desconhecida` means the scan recorded neither executed nor skipped scanners (a row older than migration 0007, a scan still running, or a failure to persist). It is never reported as complete. All three coverage values come from `orchestrator/reporting/coverage.py`, the single place that computes coverage for the bundle, the executive report and the UI.

From a generated bundle where trivy had no binary:

```json
"scanners_requested": ["semgrep", "gitleaks", "trivy"],
"scanners_executed": ["semgrep", "gitleaks"],
"scanners_failed": ["trivy"],
"scanners_failed_reason": {"trivy": "binário ausente"},
"coverage_complete": false,
"coverage_state": "incompleta",
"coverage_note": "COBERTURA INCOMPLETA: trivy não rodaram. Zero achados destes vetores NÃO significa alvo limpo."
```

("Missing binary"; "incomplete coverage: trivy did not run. Zero findings from these vectors does NOT mean a clean target.")

**Zero vulnerabilities only means clean with `coverage_complete: true`.**

## 5. target and tech_stack_hints

| Field | Meaning |
| --- | --- |
| `primary_value` | The scanned target (`unknown` if the target row is gone) |
| `asset_type` | `url`, `domain`, `host`, `port`, `image`, `repo` or `k8s_resource` |
| `label`, `contains_pii` | As registered on the target |
| `scope` | `[primary_value]`. The bundle does not carry the shield's allowlist |
| `out_of_scope` | Always `[]` today |
| `source_code_available_to_patcher` | `true` when `asset_type` is `repo`: the patcher has the code and can patch instead of only recommend |
| `tech_stack_hints` | Below |

`tech_stack_hints` is derived from evidence the scanners already produced. It is deterministic and calls no model:

| Field | Source |
| --- | --- |
| `languages` | Extension of the finding's target path (`.py`, `.js`, `.ts`, `.java`, `.go`, and others) |
| `package_managers` | A manifest name in the path (`requirements.txt`, `pyproject.toml`, `package.json`, `yarn.lock`, `go.mod`, `pom.xml`, `build.gradle`, `gemfile`, `composer.json`) |
| `runtimes` | `Dockerfile` or `docker-compose.yml` in the path |
| `servers` | Service banner in nmap findings (nginx, apache, openssh, mysql, redis, and others) |
| `source_repos`, `container_images` | The target itself, when it is `repo` or `image` |
| `frameworks` | Always `[]` today |
| `confidence` | `medium` when any signal was found, `low` when none |

## 6. summary and compliance

`summary` counts what is in `vulnerabilities`:

| Field | Meaning |
| --- | --- |
| `counts_by_severity` | `critical`, `high`, `medium`, `low`, `info`, always all five |
| `counts_by_category` | Count per `category` |
| `owasp_top10_2021` | Distinct codes (`A03`), from the AI triage |
| `top_cwes` | Up to five, most frequent first |
| `patchable_automatically_count` | Entries with `remediation.patch_strategy.confidence: high` |
| `needs_human_review_count` | The rest |

`compliance` is the same mapping as `GET /reports/{id}/compliance`, rebuilt from the stored findings:

| Field | Meaning |
| --- | --- |
| `risk_grade`, `risk_index`, `max_cvss` | Posture grade A to F, the index behind it and the highest CVSS |
| `owasp_top10_2021`, `pci_dss_4_0`, `lgpd` | Coverage per framework |
| `cwe_top25_2023` | CWEs of the scan that are in the CWE Top 25 of 2023 |
| `findings_descartadas` | How many stored findings could not be read in the current schema ("discarded findings") |
| `nota_de_integridade` | `null`, or a sentence saying the grade above left those findings out and is optimistic |

The integrity note exists because `vulnerabilities` is built from the raw rows and includes a finding that the grade, built from the validated schema, had to drop. Read `findings_descartadas` before trusting `risk_grade`.

## 7. vulnerabilities

One object per problem:

| Field | Meaning |
| --- | --- |
| `id` | `uuid5(deduped_key)`, stable across scans |
| `deduped_key` | The identity of the problem, not of the occurrence |
| `title` | As the scanner wrote it |
| `category` | Derived from the scanner, table below |
| `severity` | Adjusted by the AI triage when there is one, otherwise the scanner's |
| `severity_original` | What the scanner reported |
| `confidence` | `tentative`, `firm` or `certain` |
| `patch_priority` | 1 (urgent) to 5 ([section 8](#8-patch_priority)) |
| `classification` | `owasp_top10_2021` (from the triage), `cwe` (list), `cve` and `ghsa` (from the finding's id when it starts with `CVE-` or `GHSA`), `cvss_v3`, `epss_percentile` (always `null` today), `exploit_available` (always `false` today) |
| `discovered_by` | `tool`, `rule_id`, `rule_name` (the title), `raw_output_ref` |
| `instances[]` | Up to 3, each with `instance_id`, `location` and scrubbed `evidence`. A finding with no evidence gets one instance whose evidence is the scrubbed description |
| `remediation` | Below |
| `verification` | Below |
| `ai_triage` | `rationale`, `is_likely_false_positive`, `business_impact`, `model_used`; `null` when the finding was not triaged |

**Category and location by scanner.** The map is fixed in the exporter:

| Scanner | `category` | `location.kind` | Fields in `location` | `patch_strategy.approach` |
| --- | --- | --- | --- | --- |
| zap, nuclei | `web` | `http_endpoint` | `url`, `method` (always `GET`), `host`, `parameter`, `parameter_location`, `request_template` (the last three `null`) | `code_change` |
| nmap, greenbone | `infra` | `host_port` | `host`, `port`, `protocol` | `config_change` |
| trivy | `deps` | `container_layer` | `image`, `package`, `version` | `dependency_upgrade` |
| gitleaks, trufflehog | `secret` | `repo_path` | `path`, `line` | `secret_rotation` |
| semgrep | `sast` | `source_file` | `path`, `line` | `code_change` |
| github_exposure, dnstwist, shodan, censys, subdomain_takeover | `osint` | `domain` | `domain` | `manual` |
| checkov | `misconfig` | `file_path` | `path`, `line` | `config_change` |
| kube_bench | `k8s` | `k8s_resource` | `resource_id` | `config_change` |
| anything else | `infra` | `host_port` | `host`, `port`, `protocol` | `config_change` |

For `repo_path`, `file_path` and `source_file`, the adapters record the target as `file:line` and the exporter splits it: `src/db.py:41` becomes `"path": "src/db.py", "line": 41`. When the scanner gave no line (`app.py:?`), `path` keeps the whole value and `line` is `null`. A SAST finding counts in `needs_human_review_count`, not in `patchable_automatically_count`, because `code_change` has `medium` confidence.

**remediation:**

| Field | Meaning |
| --- | --- |
| `summary` | The triage's suggested remediation, or the scanner's, or `""` |
| `rationale` | The triage's rationale, or `""` |
| `patch_strategy` | `approach` (table above); `confidence` `high` for `dependency_upgrade` and `config_change`, `medium` otherwise; `estimated_effort` `small` for `config_change`, `medium` otherwise; `blast_radius` `module` for `code_change`, `service` otherwise |
| `code_search_patterns`, `before_after_examples` | Always `[]` today |
| `dependency_upgrade`, `config_change` | Always `null` today |
| `secret_rotation` | For `secret_rotation`: `{credential_type: "unknown", scope: "unknown", rotation_steps: []}`; otherwise `null` |
| `references` | The scanner's references |

The `patch_strategy` values are a fixed rule by category, not an analysis of the finding.

**verification:** `method` is always `rerun_scanner`, with `rerun.scanner` (the tool that found it), `rerun.scan_profile` (`focused`), `rerun.options.target` and `rerun.expected_outcome` (a sentence in English). `http_probe` is `null` and `suggested_unit_tests` is `[]`. In practice, verification means scanning again ([section 10](#10-how-a-patcher-should-consume-it)).

## 8. patch_priority

```
base = severity rank + 1        # critical 1, high 2, medium 3, low 4, info 5
tentative confidence            → base + 1, at most 5
ai_triage.is_likely_false_positive → 5
```

The severity used is the adjusted one. A finding the model marked as a likely false positive goes to the end of the queue and **stays in the bundle**: the mark is the model's guess, not a verdict.

## 9. appendix

| Field | Meaning |
| --- | --- |
| `raw_scan_artifacts` | `[{tool, path}]` pointing at the scan's HTML report on the shield's disk, or `[]` when there is none. At most one entry |
| `scrubbing_applied` | `cpf`, `cnpj`, `pan_luhn`, `cvv`, `email`, `jwt`, `aws_keys`, `github_token`, `slack_token`, `secret_assignment`, `auth_header`, `cookie_header`, `phone_br` |
| `patcher_instructions` | A fixed sentence in English. It mentions `code_search_patterns` and `before_after_examples`, which are empty today |

## 10. How a patcher should consume it

1. Check `scan.coverage_complete`. If it is `false`, what is missing is in `scan.scanners_failed_reason`; do not report the target as clean.
2. Walk `vulnerabilities` in `patch_priority` order.
3. Use `target.tech_stack_hints` for language and package manager, and `target.source_code_available_to_patcher` to decide between patching and recommending.
4. For each entry, read `instances[].location` and `remediation`, and propose the patch. For SAST, read the file and line from the location as described in [section 7](#7-vulnerabilities).
5. Treat `ai_triage.is_likely_false_positive: true` as a candidate for dismissal, not as truth.
6. Confirm by scanning the same target again and comparing by `deduped_key`, with the new scan's `coverage_complete` still `true`. Record the outcome with `POST /findings/resolve`; the status lives on the shield, not in the bundle.

Never paste a bundle into a public issue, a chat or a log: [section 2](#2-guarantees-and-where-each-one-stops) explains why it can carry a credential.

## 11. Versioning

A change that **breaks** the contract (removing a field, changing a type or a meaning) bumps the major of `schema_version`. A new optional field bumps the minor. The fields that are fixed values today (`out_of_scope`, `frameworks`, `epss_percentile`, `exploit_available`, `code_search_patterns`, `before_after_examples`, `dependency_upgrade`, `config_change`, `http_probe`, `suggested_unit_tests`) can start carrying data without a major bump, since their type does not change.

## When something does not work

- `404 scan não encontrado`: the id is wrong, or the scan was deleted (`DELETE /scans/{id}` removes its findings; the audit trail keeps the record).
- `500 falha ao gerar bundle`: read the shield's log (`roqueshield logs orchestrator`). [WHEN-IT-BREAKS.md](WHEN-IT-BREAKS.md) covers the common causes.
- The bundle has zero vulnerabilities: look at `scan.coverage_state` before believing it.
- `compliance.findings_descartadas` is above zero: some stored findings no longer validate in the current schema (typical after a rollback or with two worker versions during an update). The vulnerabilities are listed; the grade is not counting them.
