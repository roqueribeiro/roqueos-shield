# Development

*Also available in [Brazilian Portuguese](pt-BR/DESENVOLVIMENTO.md).*

> For people who change RoqueShield's code. This is the development stack: Docker Compose, Postgres and one container per piece. To **use** RoqueShield, install the standalone container instead: [GETTING-STARTED.md](GETTING-STARTED.md), and [OPERATIONS.md](OPERATIONS.md) to run it day to day. How to test is in [TESTING.md](TESTING.md); how to add a scanner, in [EXTENDING.md](EXTENDING.md); the pull request rules, in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Table of contents

1. [Development stack or standalone](#1-development-stack-or-standalone)
2. [What you need](#2-what-you-need)
3. [First start](#3-first-start)
4. [The containers](#4-the-containers)
5. [Day to day](#5-day-to-day)
6. [The web screen](#6-the-web-screen)
7. [Local gates](#7-local-gates)
8. [The CI](#8-the-ci)
9. [Backup and update of the development stack](#9-backup-and-update-of-the-development-stack)
10. [Claude Code: skills, commands and agents](#10-claude-code-skills-commands-and-agents)
11. [When something does not work](#11-when-something-does-not-work)

A note on names: `cai` is the engine's internal name. It is the Python package (`cai-orchestrator`), the admin CLI (`cai`), the Compose project (`name: cai`) and the prefix of every development container (`cai-*`). The product is RoqueShield, and the client CLI is `roqueshield`.

## 1. Development stack or standalone

There are two ways to bring RoqueShield up, and they are not the same thing.

| | Development stack | Standalone |
| --- | --- | --- |
| Who it is for | whoever changes the code | whoever uses the tool |
| How it starts | `make up` (Compose files in `docker/`) | `install.sh`, one `docker run` |
| Containers | one per piece: API, worker, Postgres, Redis, ZAP, Trivy, lab targets | one: engine, ZAP, Redis and the web screen together |
| Image | `cai-orchestrator:dev`, built on your machine | `roqueribeiro1988/roqueos-shield:vX.Y.Z-standalone`, from Docker Hub |
| Database | Postgres (`cai-postgres`), schema by `make migrate` | SQLite in the `/data` volume, tables created at boot |
| Screen at `/` | none: `/` redirects to the old dashboard at `/ui/` | the web screen from `web/` |

The development image does not carry the web screen: `.dockerignore` keeps `orchestrator/web_dist` out of the build context, on purpose, so a forgotten local build cannot leak into the engine image. To work on the screen, see [section 6](#6-the-web-screen).

To build the standalone image yourself and install it the way a user would, see [CONTRIBUTING.md](../CONTRIBUTING.md#the-standalone-image). Updating, backup and everything else about the standalone container is in [OPERATIONS.md](OPERATIONS.md).

There is also `docker/compose.prod.yml` (project `roqueshield`): the standalone image split into services with Postgres, for production. That one belongs to operations, not to development.

## 2. What you need

- **Docker Engine** (Linux) or **Docker Desktop** (WSL2 on Windows) with Compose v2.
- **make** and **bash**.
- **Python 3.13** for the tests and gates that run outside Docker (`requires-python = ">=3.13"` in `pyproject.toml`).
- **Node 22** and **yarn** if you touch `web/`. The CI uses Node 22.20.0. Never npm: the lockfile is `web/yarn.lock`.
- **8 GB of free RAM** for the full stack. The ZAP container alone has a 6 GB ceiling (`mem_limit: 6g` in `docker/compose.scanners.yml`).
- An **NVIDIA GPU** for the `cai-ollama` container. See the warning in [section 4](#4-the-containers).
- An **Anthropic or OpenAI key** is optional. Without one, scan with `make scan-no-ai`.

## 3. First start

```bash
git clone https://github.com/roqueribeiro/roqueos-shield.git
cd roqueos-shield
cp .env.example .env

# Strong secrets, without printing them. Hex, because base64 can contain "/",
# which breaks the sed expression.
for k in APP_TOKEN ZAP_API_KEY POSTGRES_PASSWORD; do
  sed -i.bak "s|^$k=.*|$k=$(openssl rand -hex 24)|" .env
done
# DATABASE_URL carries the Postgres password too: keep the two in step.
pg="$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)"
sed -i.bak "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://cai:${pg}@postgres:5432/cai|" .env
rm .env.bak

make build      # cai-orchestrator:dev, cai-kali-toolbox:dev and, if it builds, cai-expert:dev
make up         # profiles default + scanners + lab
make migrate    # alembic upgrade head against cai-postgres
```

Three things the commands above take care of, and why:

- **The API refuses to boot with the example token.** `APP_TOKEN` empty, `dev-changeme`, `dev-changeme-with-strong-random`, `changeme` or `change-me` stops the boot (`orchestrator/config.py`), unless `ALLOW_INSECURE_APP_TOKEN=true`.
- **`DATABASE_URL` in `.env.example` has the example password written in it.** Changing only `POSTGRES_PASSWORD` gives you a Postgres with one password and an API trying another.
- **Postgres reads the password only once**, when the `pgdata` volume is created. Changing it later in `.env` does nothing to an existing volume.

**What you should see** after `make up`, printed by the Makefile:

```
Stack no ar:
  orchestrator API : http://127.0.0.1:8080  (X-API-Token: $APP_TOKEN)
  zap              : http://127.0.0.1:8090
  trivy            : http://127.0.0.1:4954
  ollama           : http://127.0.0.1:11434
  juice-shop       : http://127.0.0.1:3000
  dvwa             : http://127.0.0.1:8000
```

(`Stack no ar` = stack is up.) Then check it:

```bash
curl http://127.0.0.1:8080/health
# {"status":"ok","version":"..."}

TOKEN="$(grep '^APP_TOKEN=' .env | cut -d= -f2)"
curl -s http://127.0.0.1:8080/health/full -H "X-API-Token: $TOKEN"
```

`/health` is liveness, with no auth. `/health/full` asks for the token and checks Postgres, Redis, ZAP, the LLM and whether each scanner binary exists in the image. A scanner listed under `ausentes` (missing) does not run, and its vector stays unchecked.

## 4. The containers

All of them listen on 127.0.0.1 only. Postgres and Redis publish no port: they are reachable only inside the `cai-net` network.

| Container | Compose file | Profile | Port on your machine | What it is |
| --- | --- | --- | --- | --- |
| `cai-orchestrator` | `compose.yml` | default, scanners | 8080 | the API (uvicorn) |
| `cai-worker` | `compose.yml` | default, scanners | none | the arq worker that runs the scans |
| `cai-postgres` | `compose.yml` | default, scanners | none | Postgres 16 |
| `cai-redis` | `compose.yml` | default, scanners | none | the job queue |
| `cai-ollama` | `compose.yml` | default, ai-local | 11434 | local models (reserves an NVIDIA GPU) |
| `cai-zap` | `compose.scanners.yml` | scanners | 8090 | OWASP ZAP daemon |
| `cai-trivy` | `compose.scanners.yml` | scanners | 4954 | Trivy in server mode (shared DB cache) |
| `cai-kali-toolbox` | `compose.scanners.yml` | scanners | none | Kali image kept alive for `docker exec` |
| `cai-juice-shop` | `compose.lab.yml` | lab | 3000 | vulnerable target |
| `cai-dvwa` | `compose.lab.yml` | lab | 8000 | vulnerable target |
| `cai-webgoat` | `compose.lab.yml` | lab | 8081, 9090 | vulnerable target |
| `cai-gvm-feeds`, `cai-gvm-redis`, `cai-gvm-postgres`, `cai-gvmd`, `cai-ospd-openvas` | `compose.greenbone.yml` | greenbone | none | Greenbone Community, minimal |
| `cai-gvm-gmp-tcp` | `compose.greenbone.yml` | greenbone | 9390 | GMP over TCP, for the orchestrator |
| `cai-gsa` | `compose.greenbone.yml` | greenbone | 9392 | Greenbone web UI |
| `cai-phoenix` | `compose.observability.yml` | obs | 6006, 4317 | Phoenix tracing (UI and OTLP gRPC) |
| `cai-expert` | `compose.agent.yml` | ai-agent | none | agent container, `sleep infinity` |
| `cai-caddy` | `compose.proxy.yml` | proxy | 443 | TLS reverse proxy for `cai.local` |

The scanners run inside `cai-worker`, as subprocesses. The orchestrator image carries nmap, nuclei, gitleaks, trufflehog, trivy, semgrep (with its ruleset offline in `/opt/semgrep-rules`), dnstwist and checkov (in its own venv). The `cai-kali-toolbox` container is not where scans run.

**Ollama is in the `default` profile and reserves an NVIDIA GPU** (`deploy.resources.reservations.devices`). So `make up` and `make api` both try to start it. On a machine without the NVIDIA container runtime, Docker cannot satisfy that reservation. Start the rest without it, naming the services:

```bash
docker compose --env-file .env --project-directory docker \
  -f docker/compose.yml -f docker/compose.scanners.yml -f docker/compose.lab.yml \
  --profile default --profile scanners --profile lab \
  up -d orchestrator worker postgres redis zap trivy kali-toolbox juice-shop dvwa webgoat
```

Greenbone setup (feed sync, credentials) and LM Studio are in [OPERATIONS.md](OPERATIONS.md).

## 5. Day to day

The Makefile hides the Compose flags. `make help` lists every target; these are all of them:

| Target | What it does |
| --- | --- |
| `make build` | builds `orchestrator`/`worker`, then `kali-toolbox`, then `cai-expert` (a failure on the last one is ignored) |
| `make up` | profiles default, scanners and lab |
| `make api` | profile default only: orchestrator, worker, Postgres, Redis and Ollama (the help text says "only orchestrator + db + redis") |
| `make down` | stops the stack, keeping the volumes |
| `make ps` / `make logs` | container status / follows the orchestrator and worker logs |
| `make shell` | bash in a throwaway orchestrator container |
| `make scan TARGET=<url>` | synchronous scan through the `cai scan` CLI, with AI triage; extra flags in `EXTRA=` |
| `make scan-no-ai TARGET=<url>` | the same, with `--skip-ai` |
| `make scan-api TARGET_ID=<uuid>` | `POST /scans` with nmap and zap |
| `make exposure` | OSINT scan (`cai exposure`), configured by `config/exposure_targets.yml` |
| `make smoke` | `scripts/smoke.sh`: build, up, then an active scan of the Juice Shop |
| `make migrate` / `make revision NAME=...` | `alembic upgrade head` / new autogenerated migration |
| `make test` / `make lint` | pytest / ruff and mypy, inside the orchestrator image (see the warning below) |
| `make ollama-pull` | downloads the default Ollama models |
| `make greenbone-up` / `make greenbone-down` | the Greenbone stack (feed sync of 30 min to 3 h, about 5 GB) |
| `make obs-up` / `make agent-up` / `make proxy-up` | Phoenix / `cai-expert` / Caddy |
| `make backup` | see [section 9](#9-backup-and-update-of-the-development-stack) |
| `make clean` | **deletes** the volumes and everything in `reports/` and `data/` |

`TARGET` defaults to `http://juice-shop:3000`: the name inside `cai-net`, not `localhost`.

**`make test` and `make lint` do not work as written.** They run pytest, ruff and mypy inside the orchestrator image, and that image is built with `uv export --no-dev` and copies only `orchestrator/` and `alembic.ini`; Compose mounts only `reports/`, `data/` and `config/`. So the image has no pytest, no ruff, no mypy and no `tests/`. This was read from `docker/images/orchestrator/Dockerfile`, not run here. Run the tests and linters on your machine, as the CI does ([section 7](#7-local-gates)).

**`make down` does not stop Greenbone or Caddy.** It names the profiles, but its file list does not include `compose.greenbone.yml` or `compose.proxy.yml`, so Compose does not know those services. Use `make greenbone-down`, and stop Caddy by its own file.

A scan through the API, end to end:

```bash
TOKEN="$(grep '^APP_TOKEN=' .env | cut -d= -f2)"

TARGET_ID=$(curl -s -X POST http://127.0.0.1:8080/targets \
  -H "Content-Type: application/json" -H "X-API-Token: $TOKEN" \
  -d '{"asset_type":"url","value":"http://juice-shop:3000","criticality":"medium"}' | jq -r .id)

SCAN_ID=$(curl -s -X POST http://127.0.0.1:8080/scans \
  -H "Content-Type: application/json" -H "X-API-Token: $TOKEN" \
  -d "{\"target_id\":\"$TARGET_ID\",\"scanners\":[\"nmap\",\"zap\"]}" | jq -r .id)

curl -s http://127.0.0.1:8080/scans/$SCAN_ID -H "X-API-Token: $TOKEN" | jq .state
curl -s http://127.0.0.1:8080/reports/$SCAN_ID -H "X-API-Token: $TOKEN" -o report.html
```

The admin CLI inside the image is `cai` (`python -m orchestrator.cli` is the image entrypoint, so `run --rm orchestrator <subcommand>` calls it). Its commands are `scan`, `exposure`, `serve` and `bundle`; `cai scan --help` lists `--asset-type`, `--criticality`, `--contains-pii`, `--skip-ai`, `--active-zap` and `--ajax`.

## 6. The web screen

The screen the standalone serves is a Vue 3 + Quasar app in `web/`. It is not in the development image. Two ways to work on it:

```bash
cd web
yarn install
yarn dev        # Quasar on http://127.0.0.1:9100, API calls proxied to 127.0.0.1:8080
```

`yarn dev` proxies `/setup`, `/auth`, `/settings`, `/system`, `/scans`, `/targets`, `/findings`, `/reports`, `/ui/api`, `/users`, `/health`, `/investigate` and `/exposure` to port 8080 (`web/quasar.config.js`), so it works against `make api` or `make up`.

To test the screen the way the CI does:

```bash
cd web && yarn install --frozen-lockfile && yarn build && cd ..
scripts/web_e2e.sh
```

`yarn build` writes `orchestrator/web_dist`. `scripts/web_e2e.sh` starts a throwaway shield (uvicorn, a new SQLite, no Redis) on port 8099 (`E2E_PORTA` changes it) and runs `web/e2e/standalone.e2e.mjs` against it. The secrets and the test admin password are generated into a 0600 temporary folder and never printed. Without `orchestrator/web_dist` it stops with `falta orchestrator/web_dist: rode (cd web && yarn build) antes` (web_dist is missing, build first) and exit 2. The first time, Playwright needs its Chromium: `cd web && yarn playwright install chromium`.

Texts live in `web/src/i18n/`. Screenshots in the docs come from `scripts/doc_capturas.sh`, never from a manual print.

## 7. Local gates

There is no repository gate tool here. `roqueos-gate` belongs to the RoqueOS harness, not to this repository. What this repository has are the scripts below, the same ones the CI runs. None of them needs Docker.

First, an environment with the development dependencies, as the CI builds it:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

| Command | What it holds | CI job |
| --- | --- | --- |
| `.venv/bin/ruff check orchestrator tests scripts` | lint | `lint` |
| `.venv/bin/ruff format --check orchestrator tests scripts` | format | `lint` |
| `.venv/bin/mypy orchestrator` | types (does not block the merge) | `typecheck` |
| `.venv/bin/pytest --cov=orchestrator --cov-fail-under=64` | the suite and the coverage floor | `test` |
| `python scripts/check_no_silence.py` | the silence contract, by AST | `silencio` |
| `python scripts/check_docs_fresh.py` | docs against code: scanners, adapter count, `.env.example`, stale claims, installer version, doc pairs and links | `docs` |
| `python scripts/gen_diagrams.py --check` | the SVGs in `docs/assets/` are what the generator produces now | `diagramas` |
| `.venv/bin/python scripts/openapi_snapshot.py --check` | `docs/openapi.json` matches the API (also a test: `test_openapi_snapshot.py`) | `test` |
| `uv lock --check` | `uv.lock` matches `pyproject.toml` | `lockfile` |
| `scripts/web_e2e.sh` | the web screen against a real shield | `web` |

The CI pins `ruff==0.16.5` (the `dev` extra pins the same). Another ruff version can disagree on formatting.

**What you should see** from the three Python gates on a clean tree:

```
contrato do silêncio: 27 arquivos (adapters + pipeline + exporters), nenhum zero silencioso; a persistência grava a cobertura.
doc em dia: scanners, variáveis e afirmações batem com o código.
OK: <n> diagramas em dia.
```

(No silent zero in 27 files, coverage is persisted; docs up to date; diagrams up to date.) Each one exits 1 and lists the divergences when it fails.

`scripts/release-docker.sh` is not a gate you run before a pull request. It is the maintainers' release path: it builds and publishes `vX.Y.Z` and `vX.Y.Z-standalone` to Docker Hub, and refuses a missing or stale tag, a dirty tree, a version already on the Hub, a manifest without amd64 and arm64, and a Trivy CRITICAL or HIGH with a fix.

## 8. The CI

`.github/workflows/ci.yml`, on push to `main` and on pull requests to `main`:

| Job | What it runs | When |
| --- | --- | --- |
| `lint` | ruff check and ruff format --check | always |
| `lockfile` | `uv lock --check` | always |
| `docs` | `scripts/check_docs_fresh.py` | always |
| `diagramas` | `scripts/gen_diagrams.py --check` | always |
| `silencio` | `scripts/check_no_silence.py` | always |
| `secrets` | gitleaks over the whole history, with `.gitleaks.toml` | always |
| `self-scan` | Semgrep (`p/security-audit`, `p/secrets`) over `orchestrator/` and `scripts/` | always |
| `efetividade` | `tests/integration/test_efetividade_e2e.py` with semgrep and checkov installed | always |
| `typecheck` | mypy, `continue-on-error: true` | always, never blocks |
| `test` | pytest with `--cov-fail-under=64` | always |
| `web` | lockfile age, `yarn install --frozen-lockfile`, `yarn build`, Playwright, `scripts/web_e2e.sh` | always |
| `build-image` | builds the orchestrator image, no push | pull request |
| `standalone-image` | builds engine and standalone, waits for `healthy`, checks `/setup`, the CLI and the nuclei templates | pull request |
| `publish-image` | pushes `ghcr.io/<owner>/cai-orchestrator` | push to `main`, after lint, web, typecheck, test, silencio, efetividade |

The web job also runs `web/scripts/idade-do-lock.mjs`, which fails when any version in `yarn.lock` is less than 14 days old.

## 9. Backup and update of the development stack

```bash
make backup
```

`scripts/backup.sh` writes `backups/<YYYYMMDD-HHMMSS>/cai.sql.gz` (a `pg_dump` of `cai-postgres`) and `reports.tar.gz` (the `reports/` folder). The audit trail is inside Postgres, so it goes with the dump. There is no restore target. The dump is plain SQL: restoring means feeding it to `psql` in an empty database. That path was not exercised for this document.

Update:

```bash
git pull
make build
make migrate
make up
```

`make migrate` before `make up`: the new code expects the new schema. A Postgres error `relation does not exist` is a migration that did not run.

Backup and update of the **standalone** container are a different procedure, through `install.sh --update`: [OPERATIONS.md](OPERATIONS.md).

## 10. Claude Code: skills, commands and agents

`.claude/` holds what Claude Code loads in this repository. The texts are in Portuguese.

**Commands** (`.claude/commands/`, called as `/name`):

| Command | What it runs |
| --- | --- |
| `/up`, `/down`, `/build`, `/migrate`, `/logs`, `/status` | the stack: compose up and down, build, alembic, logs, a quick diagnosis |
| `/dashboard` | starts the stack if needed and prints the `/ui/` URL with the token |
| `/test`, `/lint` | pytest, ruff and mypy inside the orchestrator image (same problem as `make test`, [section 5](#5-day-to-day)) |
| `/smoke` | `scripts/smoke.sh` |
| `/bundle <scan_id>` | `cai bundle`: the AI Fix Bundle of a scan |
| `/backup` | `scripts/backup.sh` |
| `/db-shell` | `psql` in `cai-postgres`, read-write |

Several of these call `docker compose -f docker/compose.yml` without `--project-directory docker`. `scripts/smoke.sh` explains why the Makefile passes it: with Compose v5, relative paths resolve against the project directory, and without it the build context breaks.

**Skills** (`.claude/skills/`): `cai-scan`, `cai-triage`, `cai-investigate`, `cai-exposure`, `cai-handoff-fix`, `cai-stack-status`, `cai-self-heal`, `cai-llm-debug`, `cai-add-adapter` and `cai-deploy` (which only runs when asked for explicitly). Each one is triggered by its description: "isso quebrou" (this broke) calls `cai-self-heal`, "testa o LLM" (test the LLM) calls `cai-llm-debug`.

**Agents** (`.claude/agents/`): `adapter-author` (writes a new adapter), `findings-analyst` (explores findings in the database), `fix-bundle-author` (enriches AI Fix Bundles) and `security-auditor` (reviews a diff as attacker and defender).

**Rules** (`.claude/rules/`): `scanners.md`, `testing.md`, `api.md`, `docker.md`, `triage.md`, `50-docs-vivas.md` and `60-contrato-do-silencio.md`. The last two are the ones with a gate behind them: `check_docs_fresh.py` and `check_no_silence.py`.

**Hook**: `.claude/hooks/format-python.py`, after every Edit or Write, formats the edited `.py` with ruff when ruff is installed.

`python .claude/_validate.py` validates frontmatters, JSON and internal references of `.claude/`.

## 11. When something does not work

- **`make up` stops on `cai-ollama`**: no NVIDIA runtime on this machine. Start the services by name, as in [section 4](#4-the-containers).
- **The API restarts in a loop and the log talks about `APP_TOKEN`**: the token is still the example one. Generate it as in [section 3](#3-first-start).
- **The API cannot authenticate to Postgres**: `DATABASE_URL` and `POSTGRES_PASSWORD` disagree, or the `pgdata` volume was created with another password. Align the two; for a fresh volume, `make clean` deletes it (and `reports/` and `data/` with it).
- **`relation does not exist`**: `make migrate`. Current version: `docker exec cai-postgres psql -U cai -d cai -c "SELECT version_num FROM alembic_version;"`.
- **The worker takes no jobs**: `docker logs cai-worker --tail 100` and `docker exec cai-redis redis-cli LLEN arq:queue`. Jobs in the queue and an idle worker usually mean an import error at worker start.
- **ZAP does not answer**: `docker logs cai-zap --tail 50`. The container restarts by itself after an out-of-memory kill (`restart: unless-stopped`, 6 GB ceiling).
- **`/` shows the old dashboard**: expected in the development stack. The web screen is in [section 6](#6-the-web-screen).
- **`scripts/web_e2e.sh` exits 2**: `orchestrator/web_dist` is missing, or the throwaway shield did not start (the script prints the end of its log).
- **A gate fails**: read what it printed. Each line names the file and the rule.
- **A scan fails or comes back empty**: that is the product breaking, not the stack. See [WHEN-IT-BREAKS.md](WHEN-IT-BREAKS.md).
