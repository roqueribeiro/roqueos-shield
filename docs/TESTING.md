# Testing criteria

*Also available in [Brazilian Portuguese](pt-BR/CRITERIOS-DE-TESTE.md).*

> The single list of what RoqueShield has to prove before a report goes to anyone. For people who change a scanner, the pipeline or the triage, and for whoever reviews that change. Each criterion says what to prove, how it is proven (the test, gate or manual step that runs it) and what fails it. How to set up the environment that runs these is in [DEVELOPMENT.md](DEVELOPMENT.md); how to add a scanner with its tests, in [EXTENDING.md](EXTENDING.md).

## Table of contents

1. [Why this list exists](#1-why-this-list-exists)
2. [Engagement preconditions](#2-engagement-preconditions)
3. [SAST: Semgrep](#3-sast-semgrep)
4. [Secrets: Gitleaks and Trufflehog](#4-secrets-gitleaks-and-trufflehog)
5. [Dependencies, CVE and IaC: Trivy and Checkov](#5-dependencies-cve-and-iac-trivy-and-checkov)
6. [DAST: OWASP ZAP and Nuclei](#6-dast-owasp-zap-and-nuclei)
7. [Network: Nmap and Greenbone](#7-network-nmap-and-greenbone)
8. [OSINT and external exposure](#8-osint-and-external-exposure)
9. [AI triage](#9-ai-triage)
10. [The investigation agent's leash](#10-the-investigation-agents-leash)
11. [The gates that hold it all](#11-the-gates-that-hold-it-all)
12. [What to run, by target type](#12-what-to-run-by-target-type)
13. [Running the battery](#13-running-the-battery)
14. [When something does not work](#14-when-something-does-not-work)

## 1. Why this list exists

One sentence governs the whole repository:

> **Does zero findings here mean *clean*, or *did not run*? If there is no way to tell, a signal is missing.**

A broken scanner and a safe target produce the same output: zero findings. In a report that goes to a bank's audit, that is the only difference that matters. The criteria below exist so that the same tests always run and the two are never confused.

A criterion with no mechanism to run it is decoration, so every row points at the test, gate or manual step that checks it. The test names are real: each one exists in `tests/`.

## 2. Engagement preconditions

These are not software tests. They are the terms of use, they hold for every scan against a real asset, and the CI does not replace human judgment here.

| What to prove | How it is proven | What fails it |
| --- | --- | --- |
| The target is authorized in writing | `authorization_ref` filled in on `POST /scans` when `REQUIRE_AUTH_REF=true` | 403 without the ticket or formal approval |
| The scope is closed | `LAB_ONLY=true` (the default) with `TARGET_ALLOWLIST` holding the written scope; a target outside it is refused | a target outside the allowlist runs |
| An agreed window | agreed with the asset owner before the active scan | an active scan with no window |
| Personal data does not reach an external LLM | `orchestrator/domain/scrubber.py` redacts PII and PCI before any output to an external model | evidence with a CPF or a card number reaches the provider raw |

Lab targets (Juice Shop, DVWA, WebGoat) and the engagement's own assets. Never a third party's target without authorization, never an external target "just to test".

## 3. SAST: Semgrep

| What to prove | How it is proven | What fails it |
| --- | --- | --- |
| SAST runs with egress closed | the `semgrep-rules` ruleset ships in the image (`/opt/semgrep-rules`), pinned by commit (`SEMGREP_RULES_COMMIT`) | `--config auto` with `--metrics off`: exit 0, zero rules, zero findings |
| Finds command injection | `test_efetividade_e2e.py` requires a rule with `subprocess` on the synthetic repository | `subprocess` missing from the rules that fired |
| Finds SQL by concatenation | same test, term `sql` | missing |
| Finds unsafe deserialization | same test, term `deserialization` (pickle) | missing |
| Finds a weak hash | same test, term `md5` | missing |
| Refuses a config that does not resolve | `test_semgrep_recusa_auto_em_vez_de_falhar_calado`: `start_scan` with `config=auto` raises `ValueError` | `start_scan` accepts `config=auto` and goes on quietly |

Floor: at least 5 Semgrep findings on the synthetic repository. Fewer is shallow SAST, and it fails.

## 4. Secrets: Gitleaks and Trufflehog

| What to prove | How it is proven | What fails it |
| --- | --- | --- |
| A missing or unreadable report is not a "clean repository" | `test_gitleaks_sem_report_nao_e_repo_limpo`, `test_gitleaks_report_corrompido_reprova`; `read_jsonl` in `adapters/base.py` fails when every line is unreadable and keeps the good ones plus a declared gap when only some are | `except json.JSONDecodeError: continue` turning into `{}` |
| A rotated credential does not collapse into one finding | `dedup_discriminator` on the finding, part of `deduped_key` | two distinct secrets become one |
| A shallow clone is declared | `test_gitleaks_clona_o_historico_inteiro_por_padrao`, `test_gitleaks_clone_raso_declara_a_lacuna` | `clone_depth` cuts history and the report does not say so |
| Unverified secrets are not dropped quietly | `--only-verified` is off by default; unverified findings come out MEDIUM and TENTATIVE (`test_trufflehog_nao_descarta_segredo_nao_verificado_por_padrao`); with `only_verified: true` the discard is declared (`test_trufflehog_com_only_verified_declara_o_descarte`) | unverified secrets vanish from the report |

## 5. Dependencies, CVE and IaC: Trivy and Checkov

| What to prove | How it is proven | What fails it |
| --- | --- | --- |
| IaC with a public bucket is caught | `test_efetividade_e2e.py` requires at least 3 Checkov findings and at least one `CKV_*` rule | Checkov produces no `CKV_*` |
| Checkov gets a directory, never a URL | the pipeline passes the path of the cloned repository (`test_checkov_adapter.py`) | Checkov gets `-d <url>`, logs "Directory does not exist", exits 0 with empty output |
| A missing scanner is declared, not dropped | without trivy on the machine, `scanners_skipped` holds `trivy` and `coverage_is_complete` is false (second half of the effectiveness test) | missing trivy becomes "zero CVEs" |
| An artifact Trivy could not identify is not a clean image | `test_trivy_sem_secao_de_resultado_nao_e_imagem_limpa`: no `Results` section becomes a declared gap | a scratch or distroless image reported as "no CVE" |
| Security group `0.0.0.0/0`, unencrypted disk, debug on | real findings from the synthetic repository | any of them missing |

## 6. DAST: OWASP ZAP and Nuclei

The typical web target is a single-page app, which is why these criteria are the most sensitive.

| What to prove | How it is proven | What fails it |
| --- | --- | --- |
| A SPA (Angular, React, Vue) is really crawled | `options.zap.ajax=true` starts the AJAX spider; the `full` and `active` profiles and `--active-zap` on the CLI turn on active scan and AJAX together | the traditional spider alone: zero URLs crawled on a SPA |
| Active scan tests injection, not just headers | profile `full` or `active` sets `zap.active=true` | profile `web` (passive, the default) sold as if it tested injection |
| A spider that crawled nothing is not a clean target | `test_zap_sem_url_rastreada_nao_e_app_segura`, `test_zap_conta_urls_antes_de_fechar` | an empty passive queue read as "finished" |
| AJAX spider unavailable is a gap, not silence | `test_zap_ajax.py::test_ajax_indisponivel_vira_lacuna_declarada_e_o_scan_segue` | a missing `spiderAjax` add-on closes the scan "clean" |
| Alerts paged to the end, redirects declared | `test_zap_pagina_todos_os_alertas`, `test_zap_alerta_fora_do_prefixo_vira_lacuna`, `test_zap_saude.py::test_alertas_paginados_ate_o_fim_e_redirecionamento_vira_lacuna_declarada` | one page of 500 read as the total; alerts of the redirect target vanish |
| Network tool with egress closed | nuclei runs with `-duc -ni`; the image build fails below 2000 templates (`NUCLEI_TEMPLATES_MIN`) | nuclei hangs until the timeout on a restricted network, or an image with no templates |

**Effectiveness in the lab** (needs Docker and the `lab` profile): `make smoke` runs `--active-zap` against the Juice Shop. The script does not check the result itself: it prints where the report is. The check is yours: open `reports/scan-*.html` and look for real injection findings (SQLi, XSS). Zero findings here is a failure, not a safe application.

## 7. Network: Nmap and Greenbone

| What to prove | How it is proven | What fails it |
| --- | --- | --- |
| `poll` reads the return code, not just `task.done()` | subprocess adapters return `(rc, path)` and `poll` reads `rc`; `check_no_silence.py` fails a `poll` that does not | `task.done()` read as success |
| An exposed insecure service is HIGH | `_severity_for_service` in `nmap_adapter.py`: telnet, ftp, rsh, rexec, rlogin, tftp are HIGH; smb, database and redis ports are MEDIUM | an insecure service comes out as INFO |
| Greenbone reads the GMP status, not just XML that parses | `test_greenbone_confere_o_status_do_gmp` | a GMP error response read as an empty report |

**Known limit:** nothing checks whether the Greenbone feed sync has finished. `health()` only authenticates over GMP. A scan started during the first sync (30 min to 3 h) runs against an incomplete NVT base and does not say so.

## 8. OSINT and external exposure

Read-only over public data.

| What to prove | How it is proven | What fails it |
| --- | --- | --- |
| A rate limit does not drop dorks quietly | `test_github_rate_limit_declara_dorks_nao_consultadas`, `test_github_rate_limit_na_primeira_dork_reprova` | 3 of 10 dorks run, reported as 10 |
| Shodan and Censys do not fabricate emptiness on error | `test_shodan_falha_de_busca_nao_vira_zero_exposicoes`, `test_censys_erro_sem_resultado_reprova`, and the partial-page tests | a quota error read as "nothing exposed" |
| Subdomain takeover checks each step | `test_subtake_etapa_que_falha_reprova`, `test_subtake_sem_saida_nao_e_dominio_seguro`, `test_subtake_usa_duc_e_ni_no_nuclei` | a failed step erases the following ones |
| `health()` does a round trip | building an SDK client does not count as health | an invalid key passes health and the search fails quietly |

The Censys and kube-bench adapters exist and are tested, but no production path builds them today: neither the scan factory (`_build_adapters`) nor the exposure pipeline (`orchestrator/jobs/exposure.py`).

## 9. AI triage

Over evidence already scrubbed.

| What to prove | How it is proven | What fails it |
| --- | --- | --- |
| PII and PCI do not leave for an external LLM | `scrubber.py` runs before any payload leaves; `test_scrubber.py` | CPF, card number, JWT or Bearer in the message to the provider |
| The scanner's severity is kept | triage writes `ai_triage.adjusted_severity`, never `Finding.severity` | original severity overwritten |
| A malformed LLM answer does not break the scan | `triage_batch` logs `ai.triage_parse_failed` and goes on | a parse exception breaks the pipeline |
| Data sovereignty is a switch, not a hope | `ALLOW_CLOUD_FALLBACK=false` with a local model: the cloud fallback is blocked (`test_gateway_sovereignty.py::test_cloud_fallback_blocked_when_disabled`) | silent cloud fallback with sensitive data |

## 10. The investigation agent's leash

Deep investigation runs with `dry_run=true` by default, and live execution also needs `AGENT_LIVE_EXECUTION=true`. The leash is code in `orchestrator/ai/agentic/executor.py`, not a sentence in the prompt.

| What to prove | How it is proven | What fails it |
| --- | --- | --- |
| A target outside the allowlist is refused | `test_agent_executor.py`: a command against a host outside the scope comes back refused | the command runs outside the scope |
| Brute force is forbidden in every phase | the executor denies `hydra`, `medusa`, `patator`, `ncrack` | any brute-force binary runs |
| No shell, no metacharacter to escape | `argv` as a list to `create_subprocess_exec`; an argument with a shell metacharacter is refused (`test_coleira_argv.py`) | a command built as a shell string |
| Write-to-disk flags are denied | the executor refuses flags that write, read local files or give a shell (`--os-shell`, `--sql-shell` and others) | a "read-only" scan writes on the target |
| `dry_run=true` plans, does not run | the decision comes back with `executed=false` and the reason `dry_run: comando planejado, não executado` (planned, not executed) | the command runs with dry_run on |
| Every decision, refusals included, goes to the audit | `ExecDecision.to_audit()` | a refusal with no record |

When the executor changes, the proof required at closing is a test showing the leash refuses a target outside the allowlist.

## 11. The gates that hold it all

| Gate | What it does | Mutation test |
| --- | --- | --- |
| **silencio** (`scripts/check_no_silence.py`) | fails an empty `except` in the scan lifecycle, a `poll` that decides by `task.done()`, a fabricated success payload, and a persistence that does not record coverage | four plantings, all `exit 1`; the gate's own bypasses are tests in `test_gate_do_silencio.py` |
| **efetividade** (`tests/integration/test_efetividade_e2e.py`) | builds a repository with known defects and requires a real finding from each layer | with `--config auto`, SAST does not run and the gate fails |
| **docs** (`scripts/check_docs_fresh.py`) | every buildable scanner appears in the docs, the adapter count is right, every `Settings` field is in `.env.example`, nothing is called "stub" that already runs, the doc pairs and links resolve | an undocumented scanner, a `Settings` field missing from `.env.example`, a doc calling the agent a stub |

The gate is the floor, not the ceiling. A check that has never failed is not a check: before declaring a gate done, break it on purpose and confirm that it fails.

## 12. What to run, by target type

| Target type | Scanners | Minimum criterion |
| --- | --- | --- |
| URL, SPA web app | zap (active and ajax) and nuclei: profile `full` | real injection findings; URLs crawled > 0 |
| URL, classic web app | zap (active) and nuclei | findings; AJAX not required |
| Host or IP | nmap (and greenbone when requested) | ports and services; severity by heuristic |
| Domain | profile `full`: nmap, zap and nuclei | as web plus network |
| Container image | trivy | CVEs by layer; an artifact Trivy could not identify is a declared gap |
| Repository | semgrep, gitleaks, trufflehog, trivy, checkov | a finding from each layer present in the code |
| External exposure | github, gitleaks and trufflehog on the repositories found, dnstwist, shodan, subdomain takeover | reading public data; nothing active |

Without a profile or a scanner list, each type gets its default (`_DEFAULT_SCANNERS` in `orchestrator/jobs/pipelines.py`): URL and domain get `zap`, host and port get `nmap`. In every case, a scanner incompatible with the target type is filtered out before the scan, and a scanner that could not run shows up in `scanners_skipped`, never as zero findings.

## 13. Running the battery

With the development environment from [DEVELOPMENT.md](DEVELOPMENT.md#7-local-gates):

```bash
.venv/bin/pytest                                  # unit and integration, nothing that needs Docker
python scripts/check_no_silence.py                # the silence gate
python scripts/check_docs_fresh.py                # the docs gate
.venv/bin/pytest tests/integration                # only the integration folder
.venv/bin/pytest tests/integration/test_efetividade_e2e.py -v   # needs semgrep and checkov on the PATH
make smoke                                        # the lab: active scan of the Juice Shop (Docker)
```

**What you should see** from `pytest` on a machine without checkov (measured on 2026-11-08):

```
610 passed, 8 skipped
```

The skips are the tests that need a binary that is not installed. The main effectiveness test skips without semgrep and checkov, with the reason `precisa de semgrep e checkov instalados` (needs semgrep and checkov installed). A skip is not a pass: the CI job `efetividade` installs both so it does run.

There is no `integration` marker: `pytest -m integration` selects nothing (56 deselected). The integration tests run with plain `pytest`, from `tests/integration`. `make test` runs the same `pytest -q tests/` on your checkout through `uv run --frozen --extra dev`, not in the image; [DEVELOPMENT.md](DEVELOPMENT.md#5-day-to-day) explains why.

The evidence of any delivery is the raw output of these commands, pasted with no summary. Lab scans always; never point a test at a real asset or at any external target.

## 14. When something does not work

- **The effectiveness test skips**: semgrep or checkov is not on the `PATH`. The CI installs checkov in its own venv (`checkov==3.3.15`) and links it into the `PATH`, because in the app's environment the pip resolver did not finish.
- **The SAST layer finds nothing**: look at the Semgrep config. `config=auto` is refused on purpose; a config that does not resolve gives zero rules.
- **`make smoke` closes with zero findings on the Juice Shop**: that is a failure. Check that ZAP ran active with AJAX (`--active-zap`) and that `scanners_skipped` is empty in the report.
- **A gate fails on code you did not touch**: read the line it printed. It names the file, the line and the rule. The fix is in the code or in the gate (with the new case as a test), never a silencing comment without a reason. The `# silencio-ok: <reason>` escape exists for the empty result that is really correct.
- **More on scans that break**: [WHEN-IT-BREAKS.md](WHEN-IT-BREAKS.md).
