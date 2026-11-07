# RoqueShield standalone

The whole RoqueShield in one container: the engine and its scanners, the web UI, the
REST API with Swagger, the MCP server, Redis and OWASP ZAP. No RoqueOS needed.

```bash
docker run -d --name roqueshield \
  -p 8080:8080 --shm-size=1g \
  -v roqueshield:/data \
  roqueribeiro1988/roqueos-shield:<version>-standalone
```

Open `http://localhost:8080`. The first screen creates the administrator account; after
that it is a sign-in screen. API and Swagger live at `/docs`.

## What runs inside

| Process | What it is | Exposed |
| --- | --- | --- |
| `orchestrator` | API, web UI, Swagger, MCP over HTTP, live progress (SSE) | `:8080` |
| `worker` | runs the scans (nmap, ZAP, nuclei, trivy, semgrep, gitleaks, trufflehog, checkov…) | no |
| `redis` | the job queue | `127.0.0.1` only |
| `zap` | OWASP ZAP daemon plus headless Firefox for the AJAX spider | `127.0.0.1` only |

A small Python supervisor starts them, restarts whatever crashes (1s, 2s, 4s… up to
60s) and stops them in order on `docker stop`. It runs as UID 1000; the container
needs no capability.

Everything the UI shows under **Execution** (each process's log, CPU and memory) comes
from inside the container. There is no Docker socket mounted.

## First boot and secrets

Without `APP_TOKEN`, `SESSION_SECRET`, `SECRETS_KEY` and `ZAP_API_KEY` in the
environment, the first boot generates them into `/data/secrets` (mode 0600) and reuses
them afterwards. Their values are never printed: the log says only `generated`, `file`
or `environment`. Anything you pass in the environment wins.

The AI provider key you type in **Settings → AI** is stored encrypted with
`SECRETS_KEY` and never comes back to the browser.

## Memory

ZAP's AJAX spider and active scan are the hungry part. Give the container at least
**6 GB of RAM** that is actually free. On Docker Desktop that means the VM, not the
laptop: with less, the kernel kills ZAP mid-scan and the report says so —
`zap` appears in `scanners_skipped`, and coverage is marked incomplete. It does not turn
into "zero findings".

## Everything is configurable from the environment

The environment wins over the UI. A field set by an environment variable shows up locked
in the UI as "defined by the environment" — the behaviour a regulated deployment wants.

| Variable | Default in this container | Effect |
| --- | --- | --- |
| `DATA_DIR` | `/data` | secrets, SQLite, reports, ZAP session, trivy cache |
| `DATABASE_URL` | SQLite in `/data` | point at Postgres for an immutable audit trail |
| `REDIS_URL` | embedded | point elsewhere and the embedded Redis does not start |
| `ZAP_BASE_URL` | embedded | point elsewhere and the embedded ZAP does not start |
| `LAB_ONLY`, `TARGET_ALLOWLIST`, `REQUIRE_AUTH_REF` | from the UI | lock the authorized scope |
| `LLM_MODEL`, `ANTHROPIC_API_KEY`… | from the UI | lock the AI configuration |
| `ALLOW_CLOUD_FALLBACK` | `true` | `false` forbids a local model from falling back to a cloud one |
| `MCP_ALLOW_ACTIONS` | `false` | lets MCP clients start scans (always with an authorization reference) |
| `OIDC_*` | off | single sign-on, alongside password login |

For production, `docker/compose.prod.yml` runs the same image with Postgres, Redis and
ZAP as separate services.

## CLI

`roqueshield` talks to a running shield over the API. Inside the container:

```bash
docker exec roqueshield roqueshield status
```

From anywhere else, with a token created in **Users**:

```bash
roqueshield login --server http://shield:8080        # asks for the token, no echo
roqueshield scan start https://app.example --auth-ref CHG-123 --wait --fail-on high
roqueshield report <scan_id> --format bundle -o bundle.json
```

Exit codes for pipelines: `0` done and clean at the threshold, `1` findings at or above
`--fail-on`, `2` usage or connection error, `3` the scan failed or coverage is
incomplete. `3` wins: zero findings from a scanner that did not run never exits `0`.
`ROQUESHIELD_URL` and `ROQUESHIELD_TOKEN` replace `login` in CI.

## MCP

For Claude Code, Claude Desktop or Cursor, over stdio:

```bash
claude mcp add roqueshield -- roqueshield mcp
```

Or over HTTP, `POST /mcp` with an `X-API-Token` header. Tools: `list_scans`,
`get_scan`, `get_findings`, `get_ai_bundle`, `list_targets`, and `start_scan` only when
actions are enabled. A failed or incomplete scan comes back as an error with the reason,
never as an empty list.
