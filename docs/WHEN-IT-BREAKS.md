# When it breaks

*Also available in [Brazilian Portuguese](pt-BR/QUANDO-QUEBRA.md).*

> **For whom:** whoever is looking at an error, a scan that came back strange, or a container that does not answer.
> **What is here:** symptom, cause and what to do, in the order you meet them: installing, signing in, starting a scan, reading the result, the container itself, production, and what to do when a scan touched what it should not.
> **Where to go for the rest:** how things are supposed to work is in [OPERATIONS.md](OPERATIONS.md); the first install, in [GETTING-STARTED.md](GETTING-STARTED.md).

The underlying rule of this tool: **zero findings is only "clean" when every scanner ran.** A broken scanner produces the same output as a safe target, so RoqueShield marks a scanner that did not run as skipped and the coverage as incomplete, instead of reporting silence. When you see **Incomplete coverage**, believe it.

**A note on language:** the installer prints in English when your `LANG` is not Portuguese. The container log, the `roqueshield` CLI and the API error messages are in Portuguese; they are quoted verbatim below, each with a short English gloss.

## Table of contents

1. [Installing](#1-installing)
2. [First run and signing in](#2-first-run-and-signing-in)
3. [Starting a scan](#3-starting-a-scan)
4. [Reading the result](#4-reading-the-result)
5. [AI](#5-ai)
6. [The container itself](#6-the-container-itself)
7. [Production compose](#7-production-compose)
8. [Incident response](#8-incident-response)
9. [Where to look](#9-where-to-look)

## 1. Installing

Every installer error starts with `Could not finish:` and exits with code 1.

| What you see | Cause | What to do |
| --- | --- | --- |
| `Docker is not installed.` | no `docker` command on the `PATH` | install Docker Desktop (Mac, Windows) or Docker Engine (Linux) and run the command again |
| `Docker is installed but did not answer.` | the daemon is not running, or is still starting | open Docker Desktop and wait for it to finish starting; on Linux, `sudo systemctl start docker` |
| `your user has no permission to use Docker.` | Linux: your user is not in the `docker` group | `sudo usermod -aG docker $USER`, log out and back in |
| `! Docker has about N GB of memory; RoqueShield needs 6 GB.` | Docker reports less than 5.5 GiB | a warning, not an error. Raise it in Docker Desktop (Settings > Resources > Memory); with less, a scanner may be killed mid-scan |
| `could not download roqueribeiro1988/roqueos-shield:...` | no connection to Docker Hub, or a version that does not exist | check the connection and `ROQUESHIELD_VERSION`; if the image is already on the machine, the installer uses it and says so |
| `the container did not start. If port 8080 is in use, pick another one:` | another program holds the port, most often | `curl -fsSL .../install.sh \| ROQUESHIELD_PORT=8081 sh` |
| `the container did not become healthy. The last log lines are above.` | the container stopped or the healthcheck failed | read those lines; the most common causes are in [section 6](#6-the-container-itself) |
| `3 minutes went by and it is not ready.` | a slow first boot (migrations, ZAP) or a process in a restart loop | `docker logs roqueshield`; run the installer again, it only waits again |
| `unknown option: --foo (use --update or --no-browser)` | a flag the script does not know | the script takes only `--update` and `--no-browser` (or `--atualizar`, `--nao-abrir`) |
| `the port must be a number (got 'abc').` | `ROQUESHIELD_PORT` is not a number between 1 and 65535 | fix the variable |
| `! container 'roqueshield' runs ... (this script installs ...)` | the container is from another version | a warning: it starts the old one. To update, add `--update` |
| The browser did not open, or opened a blank page | no display (a server, WSL without `wslview`), or the browser could not read the temporary page | open `http://localhost:8080` yourself; the code is in `docker exec roqueshield cat /data/secrets/SETUP_CODE` |

## 2. First run and signing in

| What you see | Cause | What to do |
| --- | --- | --- |
| `código de primeiro uso ausente ou errado` (first-run code missing or wrong), HTTP 403 | the code was not filled in, or was mistyped | `docker exec roqueshield cat /data/secrets/SETUP_CODE` and paste it whole |
| `muitas tentativas; espere antes de tentar de novo` (too many attempts; wait), HTTP 429 | wrong codes in a row from the same origin | wait the time in `Retry-After` and use the right code |
| `o primeiro uso já foi feito` (first run already done), HTTP 410 | an admin already exists | sign in; if nobody knows the password, see the next line |
| Forgot the admin password | | `docker exec -it roqueshield roqueshield reset-password <email>` (the CLI inside the container uses the `APP_TOKEN`) |
| `a senha precisa de pelo menos 10 caracteres` (the password needs at least 10 characters) | | a longer password; it also cannot start or end with a space |
| Login waits 30 s, then longer | 5 wrong passwords in a row for the same e-mail from the same IP; the wait doubles up to 15 min | wait, or reset the password. Restarting the container clears the counters |
| Everyone is slowed down together, behind a proxy | the shield sees the proxy's IP for every client | set `FORWARDED_ALLOW_IPS=<proxy ip>` ([OPERATIONS.md](OPERATIONS.md#6-beyond-localhost)) |
| Signed out by itself | the session expired (`SESSION_TTL_HOURS`, 12 h), the password changed, the user was deactivated, or `SESSION_SECRET` changed | sign in again |
| `sem servidor ou token: rode roqueshield login --server URL, ou defina ROQUESHIELD_URL e ROQUESHIELD_TOKEN` (no server or token), exit 2 | the CLI outside the container has no configuration | `roqueshield login --server <url>`, or the two variables in CI |
| `sem conexão com o RoqueShield: ConnectError: ...` (no connection), exit 2 | wrong address, or the shield is down | check the URL and `curl <url>/health` |
| `a API recusou (401): ...` (the API refused) | wrong, revoked or deactivated user's token | create a new token in **Users** |

## 3. Starting a scan

The **New scan** screen checks the target on its first step and explains the block there. The CLI and the API get the same reason as text, after `a API recusou (403): target.value rejeitado:` (the API refused: target rejected).

| What you see | Cause | What to do |
| --- | --- | --- |
| **localhost here is RoqueShield itself** / `é loopback (dentro do container, o próprio RoqueShield) e só vira alvo com o próprio endereço na allowlist` (is loopback, the container itself) | inside the container, `localhost` and `127.0.0.1` are RoqueShield, not your computer | for an app on your machine, use `host.docker.internal` (the **Use host.docker.internal** button swaps it) and allow that host |
| **Internal network address** / `em rede privada/loopback/IMDS e nao esta em TARGET_ALLOWLIST` (on a private network and not in the allowlist) | `LAB_ONLY=true` and the host resolves to a private address | an admin allows it (**Allow {host} in the scope**, or **Scope**). A non-admin asks an admin. Only allow what you are authorized to test |
| **Could not find this address** / `nao resolve em DNS` (does not resolve) | the name does not resolve inside the container. It is refused on purpose: unresolved, it could point anywhere | check the spelling and the container's DNS. A container name only resolves if both are on the same Docker network (`docker network connect`) |
| `é link-local (o metadata da nuvem) e não pode ser alvo` (is link-local, cloud metadata, cannot be a target) | `169.254.169.254` or the link-local range | no setting opens this one |
| The scope field is locked: **This container takes its scope from TARGET_ALLOWLIST** | the list comes from the environment | change the environment variable and recreate the container |
| `authorization_ref e obrigatorio (REQUIRE_AUTH_REF=true)` (an authorization reference is required), HTTP 403 | the deploy requires a ticket or contract number on every scan | fill in **Authorization reference**, or `--auth-ref` in the CLI |
| `limite de 20 chamadas por minuto em ...` (limit of 20 calls per minute), HTTP 429 | `RATE_LIMIT_PER_MINUTE` per user and route | wait a minute; raise the variable if a pipeline really needs more |
| `target.value nao pode comecar com '-'` (cannot start with '-') | a value that would be read as a flag by a scanner | fix the target |
| `scheme '...' nao permitido (apenas http/https)` | `file://`, `gopher://` and the like | http or https only |

## 4. Reading the result

| What you see | Cause | What to do |
| --- | --- | --- |
| **Incomplete coverage** | at least one scanner did not run; it is listed in `scanners_skipped` with the reason | the **Coverage** card in **Summary** and the **Execution** tab say which and why. Fix the cause and run again. Do not read the zero findings of that scanner as clean |
| `zap` skipped, or ZAP stopped mid-scan | almost always memory: below 6 GB the kernel kills ZAP | give Docker 6 GB ([OPERATIONS.md](OPERATIONS.md#8-memory)) |
| `o ZAP não rastreou NENHUMA URL sob o alvo: nada foi verificado` (ZAP crawled no URL under the target: nothing was checked) | the target is down, blocked by `robots.txt` or a WAF, or is an app made only of JavaScript | check that the target answers from inside the container; for a single-page app, the **Full** profile |
| `zap não alcançou <url> (accessUrl falhou duas vezes: ...)` (ZAP could not reach the URL) | the target is down or not reachable from the container | test from inside: `docker exec roqueshield python -c "import urllib.request as u; print(u.urlopen('<url>').status)"` |
| `<scanner>: falhou: ...` (failed) in the skipped list | the scanner crashed | the error is in the **Execution** tab and in `docker exec roqueshield roqueshield logs worker` |
| The scan is in **Failed** | the pipeline failed before finishing; **Summary** shows the phase and the reason | read the reason; `roqueshield scan show <id> --json` has the `errors` field |
| Took much longer than 13 minutes | a larger target, or the **Full** profile, which adds ZAP's active scan | normal for **Full**. The CLI gives up waiting after `--prazo` (7200 s) and exits with code 3; the scan itself keeps running |
| The CLI exited with code 3 | the scan failed, coverage is incomplete, or `--wait` ran out of time | code 3 wins over 0 and 1 on purpose: zero findings from a scanner that did not run never exits 0 |
| The **Network** profile ran only nmap | that is what it runs today, for a host, port, domain or URL | the profile description in the UI mentions "network checks"; there are none beyond nmap |
| A web target with the **Web** profile did not run nmap | for a URL or a domain, **Web** runs ZAP and nuclei; nmap only for a **Host / IP** target | use **Host / IP**, or **Full** |

## 5. AI

| What you see | Cause | What to do |
| --- | --- | --- |
| **AI not configured** in the AI triage tab | no provider key. The shield does not call any model | optional. The findings keep the scanner's classification. Set a provider in **AI** to get triage and remediation |
| An error on each call in **AI triage** | wrong key, model or endpoint, or the provider is down | the error is per call. Check the key in **AI**; `docker exec roqueshield roqueshield status` shows `llm_local` and `llm_cloud` |
| Local model configured, but it is not being used | `LLM_API_BASE` empty (the gateway goes to the cloud), the model name differs from the one loaded in LM Studio, or the container does not reach the host | set the endpoint to `http://host.docker.internal:1234/v1`, copy the model name exactly, and check `llm_local: ok` in `status` |
| Local model fails and the triage fails, with `llm.cloud_fallback_blocked` in the log | `ALLOW_CLOUD_FALLBACK=false` forbids sending the findings to a cloud model when the local one fails | intended in a regulated environment. Fix the local model; do not turn the variable on to make the error go away |
| A reasoning model (Qwen 3, DeepSeek R1) returns an empty answer | it spent the tokens thinking before answering | raise the context and output limits in LM Studio |
| The investigation only plans and never runs commands | `AGENT_LIVE_EXECUTION=false`, the default | intended. Turning it on lets an admin run the planned commands for real |

## 6. The container itself

The container log is the supervisor's: lines start with `[supervisor]`, followed by the output of each process.

| What you see | Cause | What to do |
| --- | --- | --- |
| `[supervisor] a migração falhou; a API não sobe sem o schema` (the migration failed; the API does not start without the schema), and the container exits | `alembic upgrade head` failed: a database from an unknown version, a full disk, a Postgres that does not accept the login | read the alembic lines just above it. Do not delete the volume to "fix" it: back it up first ([OPERATIONS.md](OPERATIONS.md#3-backup-and-restore)) |
| `Boot recusado por config insegura: APP_TOKEN está com um valor de exemplo/vazio` (boot refused by insecure config: example or empty APP_TOKEN) | an `APP_TOKEN` such as `dev-changeme` or `changeme` came from the environment | set a strong one (`openssl rand -hex 32`), or remove the variable so the container generates its own |
| `Boot recusado ...: REQUIRE_IMMUTABLE_AUDIT=true mas o banco é SQLite` (immutable audit required but the database is SQLite) | the audit trail is only append-only on Postgres | point `DATABASE_URL` at a Postgres, or turn the requirement off on purpose |
| `[supervisor] <process> saiu com código N` (exited with code N), again and again | a process dies and the supervisor restarts it, waiting up to 60 s | the lines before it say why; `docker exec roqueshield roqueshield logs <process>` |
| `audit.mutable_trail` warning on every boot | the default SQLite: the audit trail can be edited | expected in the standalone. For a trail that holds up in an audit, the production compose |
| The **Execution** tab shows no logs | the logs reach the tab through Redis; Redis is down | `docker logs roqueshield` has everything; restart the container |
| Lost the `SECRETS_KEY` (restored without it, or changed it) | the stored AI key can no longer be decrypted | type the AI key again in **AI** |

## 7. Production compose

| What you see | Cause | What to do |
| --- | --- | --- |
| `error while interpolating services.shield.image: required variable SHIELD_VERSION is missing a value: defina SHIELD_VERSION (ex. v0.5.0)` (set SHIELD_VERSION, e.g. v0.5.0) | compose did not find `.env`, or the variable is not in it | always `--env-file .env`: with `-f`, compose looks for `.env` in `docker/`, not at the root |
| `required variable POSTGRES_PASSWORD is missing a value`, and the same for `REDIS_PASSWORD`, `APP_TOKEN`, `SESSION_SECRET`, `SECRETS_KEY` or `ZAP_API_KEY` | all are required (`:?`) | generate them in the vault and put them in `.env` |
| The AI key cannot be saved, or the worker cannot read it | `SECRETS_KEY` is not a Fernet key | generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `/health` still answers the old version after an update | the `shield` container was not recreated, or the migration failed | `docker compose ... ps` and the `shield` service log |
| Scans pile up in **Queued** | no worker is running, or the workers do not reach Redis | `docker compose ... ps worker`, the worker log, and `REDIS_PASSWORD` equal on every service |
| `zap` or `redis` exits at start with `ZAP_API_KEY vazio` or `REDIS_PASSWORD vazio` (empty) | the variable reached the container empty; the entrypoint refuses to start a ZAP or a Redis without a key | put the value in `.env` and `up -d` again |
| `zap` stays `starting` or `unhealthy` | ZAP takes one to two minutes to open port 8090, or it was killed for memory | wait for the `start_period` (120 s); then `docker compose ... logs zap` and the 6 GB ceiling |
| A scanner fails with `Read-only file system` | the root of `shield` and `worker` is read-only; the scanner writes outside `/data` and `/tmp` | point the scanner's cache at `/data` or `/tmp`, or add a tmpfs for that path in the compose. Do not drop `read_only` |

## 8. Incident response

### A scan may have touched a target out of scope

1. **Stop at once:** `docker stop roqueshield` (in production, `docker compose ... stop worker shield`). That kills the running scans.
2. **See what ran, against what, by whom.** On the standalone, the SQLite is in the volume:

   ```bash
   docker start roqueshield
   docker exec roqueshield python -c "import sqlite3; c=sqlite3.connect('/data/shield.db'); [print(*r) for r in c.execute('select s.created_at, t.value, s.state, s.actor, s.authorization_ref from scans s left join targets t on t.id = s.target_id order by s.created_at desc limit 50')]"
   docker exec roqueshield python -c "import sqlite3; c=sqlite3.connect('/data/shield.db'); [print(*r) for r in c.execute('select created_at, actor, action, authorization_ref from audit_log order by created_at desc limit 50')]"
   ```

   In production, the same queries with `psql` in the `postgres` service. There the `audit_log` is append-only: nobody, not even an admin, rewrote it after the fact.
3. **Tell the owner of the engagement**, with the list of scans and targets, and with transparency. Do not run anything else until they decide.

### A finding exposed personal data or a credential

1. Do not run more scans against that asset until the owner decides.
2. Tell the owner of the engagement. It is the owner who decides whether there is a duty to notify a regulator.
3. The AI Fix Bundle goes through the scrubber, and so do the reports exported from the UI, which are built from it: credentials and personal data in the evidence come out redacted. The server-side HTML report (`/reports/<id>`, `roqueshield report --format html`) and the database do **not**: they keep the finding as the scanner returned it. Share the bundle or a UI export, not the HTML, and treat the volume and its backups with the same care as the data found.

## 9. Where to look

```bash
docker logs roqueshield                                   # the supervisor and every process
docker exec roqueshield roqueshield status                # version, account, each dependency
docker exec roqueshield roqueshield logs worker --tail 200
docker exec roqueshield roqueshield scan show <scan_id> --json
curl -s http://localhost:8080/health
```

And the **Execution** tab of the scan, which has the same logs with the CPU and memory of each process. If none of this explains it, open an issue with the version (`/health`), the symptom and the relevant log lines, after removing anything that identifies your target: [CONTRIBUTING.md](../CONTRIBUTING.md). A security problem in RoqueShield itself goes through [SECURITY.md](../SECURITY.md), not an issue.
