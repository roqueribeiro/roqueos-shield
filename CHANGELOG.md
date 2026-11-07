# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-11-07

### Added

- **Standalone: RoqueShield without RoqueOS.** `roqueribeiro1988/roqueos-shield:v0.5.0-standalone` runs the engine, the web UI, the REST API with Swagger, the MCP server, Redis and OWASP ZAP in one container, under a small Python supervisor (UID 1000, no capabilities). `docker/compose.prod.yml` runs the same image with Postgres, Redis and ZAP as separate services. Guide: [docs/standalone.md](docs/standalone.md).
- **Web UI** (`web/`): the RoqueShield screen of the RoqueOS front, ported (Vue 3 + Quasar), with first-run setup, password login, a **Users** section, runtime AI and scope settings, and the Execution tab reading process logs and CPU/memory from inside the container.
- **CLI `roqueshield`** with a pipeline exit-code contract (`0` clean, `1` findings at `--fail-on`, `2` usage/connection, `3` failed or incomplete coverage) and **MCP** over stdio and `POST /mcp` (read tools; `start_scan` only with actions on).
- **Accounts**: optional password per user (scrypt), `PUT /users/{id}/password`, and the last active admin cannot be deactivated or demoted.
- **Runtime settings** (`/settings/ai`, `/settings/scope`) stored in the database, secrets encrypted with `SECRETS_KEY`; fields set by the environment are locked.

### Security

- First-run setup requires a one-time code (`/data/secrets/SETUP_CODE`) or the `APP_TOKEN`, and is serialized: whoever reached the port first could become admin, and concurrent setups created several admins.
- Sessions carry a version: logout, password change and deactivation end every session issued before.
- Password login is throttled per email+IP (5 failures), and per IP across emails (50).
- The ZAP API key goes in the `X-ZAP-API-Key` header, never in the URL: an HTTP error from ZAP put the key in the worker log, and `/health` had the same path.
- `LLM_API_KEY` from the environment locks `LLM_API_BASE` too, and listing models with an address from the request sends only the key from the request.
- Security headers (CSP on the UI, `X-Frame-Options: DENY`, `nosniff`); built-in and compose Redis with a password; each supervised process only gets the secrets it uses.
- The standalone image drops ZAP's Webswing (unused in daemon mode), removing a Jetty 9.4.56 with three HIGH CVEs.
- `.trivyignore.yaml`: go-jose and x/net in the nuclei and trivy binaries, and `filelock` 3.32.7 (litellm requires `<4`; `ReadWriteLock` is not used), accepted until 2026-12-07.

### Fixed

- **nuclei never ran since 0.4**: its templates were mode 0700 and the worker (UID 1000) saw none. The image build now fails below a template floor, checked as UID 1000.
- `scans.started_at` was never written.
- Migrations also run on SQLite in the standalone (the `create_all` boot did not add new columns to existing tables).

## [0.4.1] - 2026-10-23

### Security

- **Image passes Trivy.** 0.4.0 was published and failed the release Trivy gate (never deployed): scanner CLIs bumped to nuclei 3.11.1, gitleaks 8.30.1, trufflehog 3.99.2 and trivy 0.76.0; `pip` removed from the final image (pip 26.2.2 vendors msgpack 1.1.2 and setuptools 70.3.0). What upstream has not fixed in its own latest binaries (Go stdlib/deps in gitleaks, nuclei, trivy) is accepted in `.trivyignore.yaml`, per binary path, until 2026-12-23. The secret scanner skips the semgrep rules and nuclei templates, whose example keys are detection fixtures.

## [0.4.0] - 2026-10-23

### Security

- **Non-root images (Issue #12).** The orchestrator/worker image runs as `roqueos` (UID 1000); `kali-toolbox` and `cai-expert` too. Orchestrator and worker have no capabilities left (`cap_drop: ALL`, no `cap_add`); without root, `NET_RAW` would not reach nmap anyway, which now does a connect scan (`-sT`). Splitting a raw-socket worker only for nmap stays open in #12.
- **Rate limit (Issue #11a).** `POST /scans`, `POST /exposure/scan` and `POST /investigate/{id}` allow `RATE_LIMIT_PER_MINUTE` (default 20, `0` disables) per principal and route, over the existing Redis, with an in-process fallback when Redis is down; over the limit returns 429 with `Retry-After`.
- **Credential redaction in logs and SSE (Issue #11c).** A structlog processor before the SSE ring buffer redacts argv values after secret flags (`-H`, `--cookie`, `--token`…), URL userinfo, `Bearer` tokens, `key=value` secrets and secret dict keys.
- **Dependency CVEs (Issue #13).** `python-libnmap` replaced by a `defusedxml` parser (CVE-2022-30284, XXE); `python-jose` by PyJWT 2.15 (CVE-2024-33663/33664); litellm, pillow, urllib3, aiohttp, weasyprint, strawberry-graphql bumped; the unused `agentic` extra (`cai-framework`, GHSA-4996-996j-2m9r) removed. The image now installs exactly what `uv.lock` pins.

### Fixed

- **ZAP** reported `unhealthy` forever: `ZAP_PORT=8090` now matches the daemon port; a 500 on `accessUrl` (ZAP cannot reach the target) gets one retry and then becomes declared incomplete coverage instead of an adapter crash.
- **AI triage** that silently triaged nothing: raw model names on a custom `api_base` are routed as `openai/<name>`; findings the LLM did not return get a deterministic triage that says so; one `ai.triage_incomplete` with the reason replaces a warning per finding. LiteLLM uses its bundled cost map; Phoenix tracing needs `PHOENIX_ENABLED=true`.

### Changed

- Version unified at 0.4.0 (`pyproject.toml` said 0.1.0). `scripts/release-docker.sh` is the official image release path (multi-arch, Trivy hard fail).

### Added

- **Scanner selection by asset type (IMAGE / REPO scans now actually run their
  tools)** — `run_scan` used to hardcode `[nmap, zap]` and the API's `scanners`
  field was silently dropped, so a `POST /scans` with `asset_type=image`/`repo`
  ran web scanners (which skip those types) and produced nothing. Now the
  requested `scanners` (or an asset-type default) build the adapter list:
  `url/domain→[zap]`, `host/port→[nmap]`, `image→[trivy]`,
  `repo→[gitleaks, trufflehog, trivy, checkov]`. Trivy defaults its internal
  scanners to `vuln,secret,misconfig` (CVEs + embedded secrets + Dockerfile/IaC
  misconfig). Unknown scanner names are skipped with a warning; an empty
  resolution falls back to `[nmap, zap]`. Tests: `tests/unit/test_scanner_selection.py`.
- **Finding status tracking + AI-consumable paginated queue** — findings stay
  write-once, but their _remediation status_ now persists across re-scans.
  - New `finding_status` table (migration `0006`) keyed by **`deduped_key`**
    (not finding id) so a status survives the new rows a re-scan creates for the
    same problem. Statuses: `open`/`in_progress`/`resolved`/`false_positive`/
    `wont_fix`/`risk_accepted` (`FindingStatus`).
  - `GET /findings/queue` — paginated (`offset`/`total`/`has_more`), **compact**
    (no heavy payload), **deduped by key** (one row per problem),
    **severity-ordered**, filterable by `status` (default `open`) + `min_severity`
    - `source_tool`. Built for an AI remediation loop to page through findings
      without blowing its context window.
  - `GET /findings/summary` — counts by status × severity.
  - `POST /findings/resolve` — `{deduped_key, status, note}` upserts the status
    row and writes an `audit_log` event (`finding.status_change`); requires
    `scans:run`.
  - Legacy `GET /findings` + `GET /findings/{id}` preserved, now carrying the
    effective `status`. 7 unit tests in `tests/unit/test_findings_queue.py`.
- **Authenticated scanning** — scan behind login by passing an auth context.
  - `POST /scans` accepts an `auth: { headers, openapi_url }` block. The
    `headers` (Cookie / `Authorization: Bearer` / custom) are **secrets** and
    are handled accordingly: `split_scan_auth()` keeps them **out of the
    `scans` table** (only a non-secret `authenticated` marker + the public
    `openapi_url` persist) and they ride to the worker as an **ephemeral arq
    job arg** (Redis, consumed); `redact_audit_auth()` redacts the header
    **values** in the audit log (keeps the names); the scrubber gains a
    `Cookie`/`Set-Cookie` redactor so a session cookie can't leak into
    findings/evidence/AI prompts.
  - The ZAP adapter injects the headers into every request via the **replacer**
    add-on and imports an **OpenAPI/Swagger** spec (`openapi_url`) to enumerate
    the real API surface — both best-effort (a missing add-on never fails the
    scan). Wired for ZAP + nuclei (the HTTP scanners); nmap is skipped.
  - 10 new tests (`tests/unit/test_authenticated_scanning.py`) — the security
    invariant (secret never persisted), audit redaction, Cookie scrubbing, and
    the ZAP injection; 105 unit tests total.
- **Compliance & executive reporting** (`orchestrator/reporting/compliance.py`).
  - Deterministic mapping engine: every `Finding` →
    OWASP Top 10 2021 (CWE-derived, or the AI-triage `owasp_top10` when present)
    → PCI DSS 4.0 requirements + LGPD articles (Lei 13.709/2018), plus the
    CWE Top 25 (2023) flag and a CVSS base (real `cvss_v3.score` or a
    severity band). `build_compliance_report()` aggregates per-framework
    coverage + a risk-posture **grade A–F** (never better than D with an open
    critical) + the top risks ranked by CVSS.
  - `GET /reports/{scan_id}/executive` — on-demand executive HTML with the
    risk-posture badge, the OWASP→PCI→LGPD coverage tables, CWE-Top-25 hits,
    and a critical/high table carrying CVSS + PCI per finding. (The
    `render_executive` template existed but had no endpoint and no compliance
    section.)
  - `GET /reports/{scan_id}/compliance` — the same mapping as machine-readable
    JSON (frameworks + per-finding) for the client's GRC/SIEM/audit pipeline.
  - The AI Fix Bundle now carries a `compliance` block (risk grade + framework
    coverage) alongside the per-vulnerability classification.
  - 14 new tests (`tests/unit/test_compliance.py`); 95 unit tests total.
- **Identity & RBAC** — named users + roles + per-user API tokens.
  - `orchestrator.domain.roles` — `Role` (admin/operator/auditor/viewer) +
    granular `Permission` (`users:manage`, `scans:run`, `scans:read`,
    `audit:read`, `config:manage`) + the role→permission map. Segregation of
    duties: operator runs scans but can't read the audit log; auditor reads
    everything + the audit log but can't run scans.
  - `UserRow` (`users` table, migration `0005_add_users`) — email, role,
    SHA-256 of a per-user token (the plaintext token is shown only once),
    `idp_subject` reserved for OIDC.
  - `orchestrator.api.deps` rewritten to a `Principal`-based model:
    `get_principal` resolves `X-API-Token` to either a **service principal**
    (the global `APP_TOKEN` → ADMIN, no DB hit — keeps the RoqueShield
    integration working unchanged) or a **named user**. `require_permission()`
    gate enforced on scans/targets/findings/reports/exposure + `/users`. The
    `audit_log` `actor` is now the authenticated identity, not a free string.
  - `/users` router (admin-only): create, list, set-role, deactivate,
    rotate-token. 14 new tests (`tests/unit/test_rbac.py`,
    `tests/unit/test_auth_principal.py`); 70 unit tests total.
- **SSO / OIDC login** (`orchestrator/api/routers/auth.py` + `orchestrator/auth/`).
  - `GET /auth/login` → IdP redirect; `GET /auth/callback` validates the ID
    token via authlib (JWKS signature + nonce + aud + exp), find-or-provisions
    the user (`idp_subject` then `email`; new users get `OIDC_DEFAULT_ROLE`,
    fail-closed `viewer`), audits `user.login`, and issues a **session JWT**
    (HS256, `SESSION_TTL_HOURS`). `GET /auth/me` returns the current identity.
  - `get_principal` now also accepts `Authorization: Bearer <session-jwt>` — it
    re-fetches the user from the DB so role changes / deactivation revoke
    immediately. Enabled only when `OIDC_ISSUER`/`CLIENT_ID`/`CLIENT_SECRET`
    are set (else `/auth/*` → 503).
  - New settings: `OIDC_DEFAULT_ROLE`, `SESSION_SECRET` (falls back to
    `APP_TOKEN`), `SESSION_TTL_HOURS`. New deps: `itsdangerous` (session cookie
    for the OIDC state). 11 new tests (`test_session.py`, `test_provisioning.py`,
    Bearer cases in `test_auth_principal.py`); 81 unit tests total.
- `orchestrator.audit.log_audit_event` — append-only audit logging applied to
  `POST /scans` and `POST /targets`. Backed by `audit_log` table reintroduced
  by migration `0004_restore_audit_compliance`. In Postgres, UPDATE/DELETE on
  `audit_log` are rejected by trigger.
- `orchestrator.domain.target_validator.validate_target_value` — rejects
  argv-injection attempts (values starting with `-`) and SSRF to private,
  loopback, link-local, and IMDS networks when `LAB_ONLY=true`. Honors
  `TARGET_ALLOWLIST` (hostname, IP, CIDR, or `*.domain`).
- New settings: `LAB_ONLY` (default `true`), `TARGET_ALLOWLIST` (CSV or JSON
  array, default empty), `REQUIRE_AUTH_REF` (default `false`). When enabled,
  `REQUIRE_AUTH_REF` forces every `POST /scans` to include an
  `authorization_ref` recorded in the audit log.
- Optional `cleanup(handle)` method on all 9 subprocess scanner adapters.
  Backed by `orchestrator.adapters._cleanup.cleanup_subprocess_handle`,
  called automatically by the pipeline in a `finally` block to drain orphan
  asyncio tasks and remove temp directories (H7 in the security audit).
- `DELETE /scans/{id}` (204) — permanently removes a scan and its dependents
  (`findings`, `ai_runs` via the `scan_id` FK). Audits `scan.delete` into the
  append-only `audit_log` **before** deleting.
- Test suite expanded from 24 to 56 tests:
  scrubber-in-triage coverage, `target_validator` H4/H5 cases, the cleanup
  helper, and a `run_scan` scan-id regression test.

### Changed

- `run_scan` AI triage now runs on **every** finding (`skip_severities=set()`),
  not just `medium+`. Hardened targets often yield only `info`/`low` findings;
  skipping them meant the AI never ran ("connected a key but it isn't using
  AI"). The AI triage is the value prop, so it always runs.
- `orchestrator.ai.analyzer._finding_to_compact` now applies `scrub()` to
  `title`, `description`, and `evidence_snippets` before any payload leaves
  the orchestrator. Previously the scrubber lived in `reporting/exporters`
  only, so AI triage received unredacted PII/PCI (C1 in the security audit;
  LGPD Art. 46 / PCI DSS Req. 3).
- `orchestrator.api.deps.require_token` uses `hmac.compare_digest` to mitigate
  token timing attacks.
- `orchestrator.api.routers.ui._ui_token` accepts `?token=` query parameter
  only on `/ui/api/events` (SSE has no header support). All other UI endpoints
  now require `X-API-Token` header to prevent token leakage via logs,
  Referer, and browser cache.
- `orchestrator.domain.scrubber._PHONE_BR` regex anchored with `(?<!\d)` /
  `(?!\d)` boundaries to stop greedy matches inside long numeric tokens
  (closes issue #6).
- `orchestrator.adapters.greenbone_adapter` uses `defusedxml` instead of
  `xml.etree.ElementTree` to mitigate XXE / billion-laughs in untrusted XML
  (H6 in the security audit).
- Bumped `litellm` from `>=1.55.0` to `>=1.70.0` (rate-limit / prompt-handling
  fixes, addresses CVE backlog).
- Bumped `authlib` from `>=1.3.2` to `>=1.7.0` (CVE-2024-37568 — OIDC
  implicit grant).
- Added `defusedxml>=0.7.1` runtime dependency.

### Fixed

- `run_scan` now updates the `scan_id` it was given (created by `POST /scans`,
  the id the UI/SSE watches) instead of minting a fresh `uuid4()`. Before, the
  results landed under a different id and the requested scan stayed `pending`
  forever in the UI. `_ensure_scan_row` upserts the existing row. Regression:
  `tests/unit/test_pipeline_scan_id.py`.

### Security

- Closes C1, C2, H1, H4, H5, H6, H7 from the internal v0.1 security audit.
- AI triage path is now PII/PCI-safe by default. Operators should re-validate
  their custom `LLM_API_BASE` (e.g., LM Studio) but the scrubber runs
  unconditionally regardless of provider.

## [0.1.0] - 2026-05-11

### Added

- Initial public release of CAI (Continuous AI Security).
- FastAPI orchestrator + arq worker queue + Postgres persistence + Redis broker.
- 15 scanner adapters following the `ScannerAdapter` Protocol:
  Nmap, OWASP ZAP, Nuclei, Trivy, Checkov, Gitleaks, Trufflehog, dnstwist,
  kube-bench, Greenbone/OpenVAS, Shodan, GitHub Code Search, Censys,
  Subdomain Takeover (subfinder + httpx + nuclei), and a base Protocol.
- Canonical `Finding` schema (Pydantic v2) with dedup heuristics.
- PII / PCI scrubber that redacts CPF, CNPJ, PAN, JWT, AWS keys, and BR phone
  numbers before any prompt leaves the orchestrator.
- AI triage gateway via `litellm` supporting Anthropic, OpenAI, Ollama,
  LM Studio, and OpenRouter as a single backend abstraction.
- AI Fix Bundle JSON exporter (schema 1.0.0) for handoff to AI patchers
  (Claude Code, Cursor, Copilot).
- HTML technical and executive reports + optional DefectDojo export.
- Append-only audit log enforced both at the application and Postgres-trigger
  layer.
- Modular Docker Compose profiles: `default`, `scanners`, `lab`,
  `greenbone`, `obs`, `proxy`, `ai-agent`.
- Alembic migrations and SQLModel async support (SQLite for dev, Postgres
  for prod).
- `lab` profile with intentionally vulnerable test targets
  (Juice Shop, DVWA, WebGoat).
- Developer ergonomics: `make build/up/migrate/smoke/test/lint/down`, CLI
  via Typer (`cai`), structured logs via structlog.

### Security

- LGPD-aware compliance gates: `LAB_ONLY`, `TARGET_ALLOWLIST`,
  `REQUIRE_AUTH_REF`, mandatory `authorization_ref` for active scans in
  production mode.

[Unreleased]: https://github.com/roqueribeiro/roqueos-shield/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/roqueribeiro/roqueos-shield/releases/tag/v0.1.0
