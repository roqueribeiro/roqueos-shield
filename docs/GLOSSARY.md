# Glossary

*Also available in [Brazilian Portuguese](pt-BR/GLOSSARIO.md).*

The CLIs, the API and the code print and name many things in Portuguese. Where a term shows up that way, the Portuguese word is given in parentheses next to the English one.

## Glossary

| Term | What it is here | Where to read more |
| --- | --- | --- |
| **RoqueShield** | The product: continuous security testing with AI triage, for regulated environments | [../README.md](../README.md) |
| **Engine** (`cai`) | The internal name of the engine that runs scans: package `cai-orchestrator`, containers `cai-*`, admin CLI `cai`. Same software as RoqueShield, older name | [REFERENCE.md](REFERENCE.md#3-the-cai-admin-cli) |
| **Standalone** | The single-container image (`roqueribeiro1988/roqueos-shield:<version>-standalone`) with API, worker, Redis, ZAP and the screen, started by `install.sh` | [REFERENCE.md](REFERENCE.md#1-the-installer-installsh) |
| **Supervisor** | The PID 1 of the standalone container (`orchestrator/standalone/supervisor.py`): generates the secrets, starts Redis, ZAP, API and worker, restarts whoever falls | [REFERENCE.md](REFERENCE.md#10-files-and-volumes) |
| **First-run code** (`código de primeiro uso`, `SETUP_CODE`) | The code `POST /setup` requires to create the first admin. Generated in `/data/secrets/SETUP_CODE`; the installer puts it in the URL fragment so it never reaches the server | [REFERENCE.md](REFERENCE.md#1-the-installer-installsh) |
| **Service token** (`APP_TOKEN`) | The token that maps to the `admin` service principal (`service@local`). The boot refuses example values | [REFERENCE.md](REFERENCE.md#4-rest-api) |
| **User token** | A per-user token sent in `X-API-Token`, stored as SHA-256 and shown once. The way the CLI, CI and MCP authenticate | [REFERENCE.md](REFERENCE.md#4-rest-api) |
| **Role** (`papel`) and **permission** | Four roles (`admin`, `operator`, `auditor`, `viewer`), each a fixed set of five permissions (`users:manage`, `scans:run`, `scans:read`, `audit:read`, `config:manage`) | [REFERENCE.md](REFERENCE.md#9-roles-and-permissions) |
| **Target** (`alvo`) and **asset type** | What a scan points at, registered with `POST /targets`. Asset types: `url`, `domain`, `host`, `port`, `image`, `repo`, `k8s_resource` | [REFERENCE.md](REFERENCE.md#8-scan-profiles) |
| **Scope** (`escopo`) | The set of targets the instance is authorized to test: `LAB_ONLY` plus the allowlist plus `REQUIRE_AUTH_REF`. Checked when a target is registered and again when a scan starts | [OPERATIONS.md](OPERATIONS.md) |
| **Allowlist** (`TARGET_ALLOWLIST`) | The written list of authorized targets: hostnames, IPs, CIDRs, `*.domain`. Empty by default | [REFERENCE.md](REFERENCE.md#6-environment-variables) |
| **`LAB_ONLY`** | On by default. Blocks private, loopback, link-local and cloud metadata addresses that are not in the allowlist. Loopback and metadata stay blocked even with it off | [REFERENCE.md](REFERENCE.md#6-environment-variables) |
| **`authorization_ref`** | The reference to the written authorization of a scan (ticket, change). Goes to the audit trail; required when `REQUIRE_AUTH_REF=true` and always for MCP's `start_scan` | [REFERENCE.md](REFERENCE.md#4-rest-api) |
| **Audit trail** (`trilha de auditoria`, `audit_log`) | Every sensitive action (scan created or deleted, login, setup, investigation and its commands, settings) recorded before it happens. Append-only on Postgres by trigger; editable on SQLite, which `REQUIRE_IMMUTABLE_AUDIT=true` refuses | [THREAT-MODEL.md](THREAT-MODEL.md) |
| **Locked field** (`locked`) | An AI or scope setting that came from the environment: the screen shows it and cannot change it. The environment wins over the screen | [REFERENCE.md](REFERENCE.md#6-environment-variables) |
| **Adapter** | The code that wraps one scanner behind the `ScannerAdapter` protocol (`health`, `start_scan`, `poll`, `fetch_results`, `normalize`). There are 15 | [EXTENDING.md](EXTENDING.md) |
| **Scanner** | The tool an adapter drives (nmap, ZAP, nuclei, trivy, semgrep...). Nine can be built by a regular scan, five more by the OSINT pipeline | [REFERENCE.md](REFERENCE.md#7-scanners-and-their-options) |
| **Profile** (`perfil`) | The `profile` of a scan: `web`, `network` or `full` pick the scanners per asset type; `full` and `active` also turn on ZAP's active scan; `exposure` runs the OSINT pipeline on the target's domain. Any other value is refused with 422 | [REFERENCE.md](REFERENCE.md#8-scan-profiles) |
| **Active scan** | ZAP sending real injection payloads, with the AJAX spider. Off in `web`, on in `full`. Slower and more intrusive | [REFERENCE.md](REFERENCE.md#8-scan-profiles) |
| **Scanner options** (`options`) | The per-scanner settings `POST /scans` accepts, from a closed list with type and range. Anything else is refused with the field's name | [REFERENCE.md](REFERENCE.md#7-scanners-and-their-options) |
| **Authenticated scanning** | A scan with `auth.headers` (cookie, authorization) and an optional `openapi_url`. The header values never reach the database: they ride only in the job and are redacted in the audit | [REFERENCE.md](REFERENCE.md#4-rest-api) |
| **Exposure** (OSINT) | The read-only pipeline over public data: GitHub dorks, gitleaks and trufflehog on found repos, dnstwist, shodan, subdomain takeover. Runs from `POST /exposure/scan`, `cai exposure`, or a scan with profile `exposure` (on the target's domain) | [REFERENCE.md](REFERENCE.md#3-the-cai-admin-cli) |
| **Finding** (`achado`) | A problem a scanner reported, normalized to the canonical `Finding` model: severity, title, location, evidence, source tool | [ARCHITECTURE.md](ARCHITECTURE.md) |
| **`deduped_key`** | A stable hash of a finding. Deduplication keeps the most severe one per key, and the findings queue and resolution work per key, across scans | [REFERENCE.md](REFERENCE.md#4-rest-api) |
| **Triage** (`triagem`) | The AI pass over every finding after deduplication: adjusted severity, rationale, likely false positive, business impact, remediation, OWASP category. It never overwrites the scanner's severity; it goes in `ai_triage.adjusted_severity` | [ARCHITECTURE.md](ARCHITECTURE.md) |
| **Scrubber** | `orchestrator/domain/scrubber.py`: removes personal and card data (CPF, CNPJ, card numbers, CVV, e-mail and others) from findings before they go to an external model | [THREAT-MODEL.md](THREAT-MODEL.md) |
| **Redaction** (`redação`) | Different from the scrubber: removes credentials (bearer tokens, cookies, `user:password@` in URLs) from logs and from the live log stream before anyone sees them | [THREAT-MODEL.md](THREAT-MODEL.md) |
| **Cloud fallback** | When a local model fails, the gateway may fall back to `LLM_FALLBACK_MODEL` in the cloud. `ALLOW_CLOUD_FALLBACK=false` forbids it, and the triage fails instead | [REFERENCE.md](REFERENCE.md#6-environment-variables) |
| **Coverage** (`cobertura`) | Whether every scanner the scan asked for actually ran. Three states: complete, incomplete, unknown (`completa`, `incompleta`, `desconhecida`). Only complete allows reading zero findings as clean | [REFERENCE.md](REFERENCE.md#4-rest-api) |
| **Incomplete coverage** (`cobertura incompleta`) | At least one scanner did not run. The screen, the reports, the bundle, the CLI (exit 3) and MCP (`isError: true`) all say so. A scan in which none ran ends as `failed` | [WHEN-IT-BREAKS.md](WHEN-IT-BREAKS.md) |
| **`scanners_ran`** / **`scanners_skipped`** | What really ran, and what did not with the reason (scanner to message). The source of the coverage state | [REFERENCE.md](REFERENCE.md#4-rest-api) |
| **`coverage_gaps`** | A field of an adapter's raw result for a partial check (an unreadable line, a page that did not load). The pipeline turns it into an INFO finding, so the gap shows up in the report and the bundle | [EXTENDING.md](EXTENDING.md) |
| **`ScanIntegrityError`** | The exception an adapter raises when it cannot vouch for its result (missing output, unparseable report, zero rules loaded). The pipeline records the scanner in `scanners_skipped` | [EXTENDING.md](EXTENDING.md) |
| **Silence contract** (`contrato do silêncio`) | The rule that a broken scanner must never look like a clean target: return `[]` only if it ran and found nothing, raise `ScanIntegrityError` if it could not check, fill `coverage_gaps` if it checked in part. Enforced by `scripts/check_no_silence.py` in CI | [EXTENDING.md](EXTENDING.md) |
| **Exit-code contract** | `roqueshield scan start --wait` and `scan watch` exit 0 (clean), 1 (finding at or above `--fail-on`), 2 (usage or connection), 3 (failed or incomplete coverage). 3 beats 0 and 1 | [REFERENCE.md](REFERENCE.md#exit-codes) |
| **AI Fix Bundle** | The JSON (schema 1.0.0) with deduplicated, prioritized findings, where to fix and how to verify, for another agent to patch the code. `GET /reports/{id}/ai-bundle`, `roqueshield report`, `cai bundle` | [AI-FIX-BUNDLE.md](AI-FIX-BUNDLE.md) |
| **Executive report** | HTML for whoever decides: risk grade from A to F, coverage warning and compliance mapping (OWASP, PCI DSS, LGPD) | [REFERENCE.md](REFERENCE.md#4-rest-api) |
| **Investigation agent** (`agente de investigação`) | `POST /investigate/{finding_id}`: a ReAct loop in which the model plans commands against one finding, sees the output and goes on. With `AGENT_ENABLED=false` it falls back to a single-prompt opinion | [INTEGRATIONS.md](INTEGRATIONS.md) |
| **Leash** (`coleira`) | The checks in `orchestrator/ai/agentic/executor.py` that every agent command passes before running: per-phase allowlist of binaries (recon, exploit), scope, no shell nor metacharacters, `dry_run`, timeout. Written in code, not in the prompt | [THREAT-MODEL.md](THREAT-MODEL.md) |
| **`dry_run`** | Default `true` in the investigation: the agent plans and shows the commands, and nothing runs | [REFERENCE.md](REFERENCE.md#4-rest-api) |
| **`AGENT_LIVE_EXECUTION`** | Off by default. Only with it on, and only for someone with `config:manage`, does `dry_run=false` run the planned commands | [REFERENCE.md](REFERENCE.md#6-environment-variables) |
| **Kali sidecar** (`cai-kali-toolbox`) | The optional container from `docker/compose.scanners.yml` where the agent's commands run isolated. With `AGENT_EXECUTOR=auto` it is used when up; the standalone image does not start it, and the commands run in-process under the same leash | [ARCHITECTURE.md](ARCHITECTURE.md) |
| **MCP** | Model Context Protocol: how an AI agent (Claude Code, Claude Desktop, Cursor) calls RoqueShield. Over stdio (`roqueshield mcp`) or HTTP (`POST /mcp`), with read tools and, opt-in, `start_scan` | [REFERENCE.md](REFERENCE.md#5-mcp-server) |
| **MCP actions** | The tools that act (today, `start_scan`). Off by default: `ROQUESHIELD_MCP_ACTIONS=1` on stdio, `MCP_ALLOW_ACTIONS=true` on HTTP | [REFERENCE.md](REFERENCE.md#5-mcp-server) |
| **Rate limit** | A cap of `RATE_LIMIT_PER_MINUTE` calls per principal on `POST /scans`, `POST /exposure/scan` and `POST /investigate/{id}`. Over it, 429 | [REFERENCE.md](REFERENCE.md#4-rest-api) |

## Frequently asked questions

### Zero findings: is the target clean?

Only if coverage is complete (`coverage_complete: true`). With incomplete or unknown coverage, zero findings means some vector was not checked. The CLI exits 3 and MCP answers with `isError: true` in that case. See [WHEN-IT-BREAKS.md](WHEN-IT-BREAKS.md).

### Why do I see `cai` everywhere?

It is the engine's internal name, from before the product was called RoqueShield. The package, the containers of the development stack and the admin CLI still use it. The CLI for users is `roqueshield`.

### Does the agent run commands against my target by itself?

Not by default. The investigation runs with `dry_run=true` and only plans. Running for real needs `AGENT_LIVE_EXECUTION=true` on the server and an admin asking for `dry_run=false`, and every command still passes through the leash and goes to the audit trail.
