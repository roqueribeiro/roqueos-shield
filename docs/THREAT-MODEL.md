# Threat model

*Also available in [Brazilian Portuguese](pt-BR/MODELO-DE-AMEACAS.md).*

> Who could abuse RoqueShield, how, and what in the code stops them. For whoever operates a shield in a regulated environment, reviews its security, or changes a control. Each mitigation names the file that implements it; what is not enforced by code is called advice or a known limit, not a control. Updated with the independent security review of November 2026 (CHANGELOG `[0.5.0]` and `[0.5.1]`).
>
> How to report a vulnerability, and the hardening checklist, are in [SECURITY.md](../SECURITY.md). Variables are in [REFERENCE, section 6](REFERENCE.md#6-environment-variables).

## Table of contents

1. [The premise](#1-the-premise)
2. [Actors and scenarios](#2-actors-and-scenarios)
3. [Sensitive data](#3-sensitive-data)
4. [Scope and target validation](#4-scope-and-target-validation)
5. [Scanner options](#5-scanner-options)
6. [The AI agent and its command leash](#6-the-ai-agent-and-its-command-leash)
7. [Accounts, tokens and first run](#7-accounts-tokens-and-first-run)
8. [The standalone container](#8-the-standalone-container)
9. [AI triage and the model gateway](#9-ai-triage-and-the-model-gateway)
10. [The audit trail](#10-the-audit-trail)
11. [Known limits](#11-known-limits)
12. [Out of scope](#12-out-of-scope)

---

## 1. The premise

RoqueShield fires active scans at targets someone else owns, operated by a small team, often in a regulated environment. The most likely attacker is not an outsider: it is **the operator**, with a legitimate credential, pointing the tool at the wrong target. So the scope check and the authorization reference come before any packet leaves, refusing is the default, and the controls that matter most are the ones that do not depend on the operator getting it right.

The second shape of risk is the tool turning on itself: a target, a scanner output or a model answer that makes the shield reach its own services, its own secrets or the cloud metadata endpoint. Most of the November review was about that.

## 2. Actors and scenarios

| Actor | Has | Scenario | Mitigation |
| --- | --- | --- | --- |
| Careless operator | `operator` token | Points at production thinking it is dev, or at an internal address | `LAB_ONLY=true` (default) with `TARGET_ALLOWLIST`; `REQUIRE_AUTH_REF`; [section 4](#4-scope-and-target-validation) |
| Malicious operator | `operator` token | Unauthorized scan; uses scanner options to read files or reach other hosts | Closed option list ([section 5](#5-scanner-options)); `authorization_ref` and `scan.create` in the audit trail; RBAC |
| Anyone who reaches the port first | Network access, no account | Becomes admin before the owner | `/setup` needs the one-time code or the `APP_TOKEN`, is serialized and throttled ([section 7](#7-accounts-tokens-and-first-run)) |
| Password guesser | Network access | Brute-forces the login or the setup code | Per email+IP and per IP throttle, scrypt |
| Hostile target | Controls what the scanner reads | Prompt injection in evidence; DNS that re-points to an internal address; a URL the parsers read differently | Scrubber and no command runs by default ([section 6](#6-the-ai-agent-and-its-command-leash)); hard loopback/link-local guard; backslash and control characters refused |
| The AI model | Proposes commands | Reads `/data/secrets`, calls the shield's own API, scans the metadata endpoint | `AGENT_LIVE_EXECUTION=false` by default; the leash checks the whole argv |
| Compromised scanner process | Code execution as the worker's user | Reads secrets and the database | Per-process environment in the standalone; a known limit beyond that ([section 11](#11-known-limits)) |
| Supply chain | A poisoned dependency or base image | Code execution in the engine | `uv.lock`; Trivy on the image before the final tag (`scripts/release-docker.sh`); `.trivyignore.yaml` with expiry dates |
| Thief of a backup or a volume | The `/data` volume or a Postgres dump | Reads the `APP_TOKEN`, the `SECRETS_KEY` and every finding | Advice, not a control: treat the backup as a secret, encrypt at rest |

## 3. Sensitive data

| Data | Where it appears | Treatment |
| --- | --- | --- |
| Card numbers, CPF, e-mail, tokens in HTTP traffic | `Finding.evidence` | `scrubber.py` before the model and in the AI Fix Bundle evidence |
| Secrets found by gitleaks and trufflehog | `evidence.snippet` of the finding | **Not redacted** by the scrubber when the pattern is not on its list (GitHub and Slack tokens, passwords). See [AI-FIX-BUNDLE.md](AI-FIX-BUNDLE.md#2-guarantees-and-where-each-one-stops) |
| Headers for authenticated scans | The job in Redis | Never written to `scans`; values redacted in the audit entry (`redact_audit_auth`) |
| `APP_TOKEN`, `SESSION_SECRET`, `SECRETS_KEY`, `ZAP_API_KEY`, `REDIS_PASSWORD`, `SETUP_CODE` | `/data/secrets` (standalone) or the environment | Generated on first boot, never printed; files `0600` |
| AI provider key set in the UI | The database | Encrypted with `SECRETS_KEY`; the audit entry records only "(trocado)" ("changed") |
| User tokens and passwords | The database | Token stored as a hash; password with scrypt |
| `authorization_ref` | `scans` and the audit trail | Append-only on Postgres ([section 10](#10-the-audit-trail)) |

## 4. Scope and target validation

`orchestrator/domain/target_validator.py` runs when a target is created (`POST /targets`), again when a scan is queued (`POST /scans`), on `auth.openapi_url`, and inside the agent's leash. `POST /targets/check` runs it without creating anything and says why a target is refused.

**Always refused, whatever the configuration:**

- a value starting with `-` (flag injection into the scanner's argv);
- backslash, whitespace and control characters: Python's URL parser and the browser disagree on the host of `http://127.0.0.1:8090\@example.com/`, so the validator would see one host and ZAP would go to another;
- any scheme other than `http` and `https` in a URL;
- a repo URL with credentials in it;
- **link-local**, which includes the cloud metadata endpoint `169.254.169.254`: never, not with `LAB_ONLY=false`, not with a name on the allowlist;
- **loopback**: only when the allowlist holds the address itself (`127.0.0.1`, `127.0.0.0/8`, `::1` or `localhost`). A *name* on the allowlist does not open loopback, because a name allowed while it resolved to the home network can later resolve to `127.0.0.1` (DNS rebinding). An IPv6 that wraps `127.0.0.1` (NAT64, 6to4, IPv4-mapped) is treated as loopback.

This is the "hard guard" (`_guarda_dura`). Inside the container, loopback is the shield itself: the API, Redis and ZAP.

**With `LAB_ONLY=true` (the default)**, a host that is not on `TARGET_ALLOWLIST` is also refused when it is private, reserved, multicast, CGNAT (`100.64.0.0/10`, the Tailscale range), `198.18.0.0/15`, NAT64 or 6to4, or when any address it resolves to is. A name that does not resolve is refused too (fail closed). Allowlist entries can be a host, a CIDR or `*.domain`. `LAB_ONLY=false` turns this part off and leaves the hard guard.

Checked here, with `LAB_ONLY=true` and an empty allowlist:

```
RECUSADO http://127.0.0.1:8080/ -> host '127.0.0.1' é loopback (dentro do container, o próprio RoqueShield) e só vira alvo com o próprio endereço na allowlist
RECUSADO http://169.254.169.254/ -> host '169.254.169.254' é link-local (o metadata da nuvem) e não pode ser alvo
RECUSADO 127.0.0.1:6379/tcp -> host '127.0.0.1' é loopback (...)
RECUSADO http://127.0.0.1:8090\@example.com/ -> target.value com barra invertida, espaço ou caractere de controle
RECUSADO http://100.64.1.1/ -> host '100.64.1.1' em rede privada/loopback/IMDS e nao esta em TARGET_ALLOWLIST
```

(Loopback "is RoqueShield itself inside the container and is only a target with its own address on the allowlist"; link-local "is the cloud metadata and cannot be a target"; "backslash, space or control character"; "private network and not on the allowlist".) The third line is a `port` target: before 0.5.1, that type skipped the check and reached the container's own Redis.

**Authorization.** With `REQUIRE_AUTH_REF=true`, `POST /scans` without `authorization_ref` is `403`. The default is `false` in the image and `true` in `docker/compose.prod.yml`.

## 5. Scanner options

`ScanIn.options` used to be a free dict passed to the adapter: `nmap.nmap_args` became nmap's argv (extra targets, `-oN` over files, `--script`), and `nuclei.templates` and `semgrep.config` took any path. Now `orchestrator/domain/opcoes.py` holds a closed list per scanner, with type and range, and `POST /scans` answers `422` naming the first field that is not on it. Examples: nmap accepts no option at all; semgrep `config` accepts only `auto` or a registry pack `p/...`; nuclei accepts `rate_limit` (1 to 500) and `severity`. The full list is in the [REFERENCE](REFERENCE.md).

## 6. The AI agent and its command leash

The investigation (`POST /investigate/{finding_id}`) runs a model in a loop that proposes security commands. The model is not trusted; `check_command()` in `orchestrator/ai/agentic/executor.py` decides, and it is a pure function with no I/O.

**It only plans, by default.** `AGENT_LIVE_EXECUTION=false` is the default. With it off, `dry_run=false` gets `403 execução real do agente desligada` ("real execution of the agent is off"), and the executor forces `dry_run` on its own as well, so a caller that skips the route does not skip the lock. With it on, `dry_run=false` still needs an admin (`config:manage`). `dry_run=true`, the default of the request, returns the commands the agent would run and runs none.

**What the leash checks, before any command:**

1. **Binary per phase.** Recon: `nmap`, `naabu`, `httpx`, `subfinder`, `dig`, `host`, `nslookup`, `whois`, `curl`, `openssl`. Directed exploitation: `sqlmap`, `nuclei`, `nikto`, `curl`, `openssl`. Brute force, DoS, fuzzers, shells and interpreters are refused by name.
2. **No shell.** The command is an argv list for `create_subprocess_exec`, and an argument with a shell metacharacter (`; | & $ \` > <`, newline) is refused anyway, as a sign of injection.
3. **Every argument, not only the target.** Before 0.5.1 the leash checked only the finding's target, so `curl file:///data/secrets/APP_TOKEN`, `curl -d @file`, `curl http://127.0.0.1:8080/` and `nmap 169.254.169.254` were allowed with a valid target. Now every URL, host, IP, numeric address (`127.1`, `0x7f000001`), path and `@file` in the argv must be the target itself; schemes other than http(s) are refused; CIDR ranges are refused.
4. **Flags that read files, write files or redirect the connection** are refused: `-o*`, `--script`, `-iL`, `-iR`, `--os-*`, `--sql-shell`, sqlmap `--alert`, `--tamper`, `-r`, curl `--config`, `--resolve`, `--proxy`, `-L`, and more.
5. **curl has a list of what it may use**, because it has more than 250 options and dozens touch files: short `-sSIikvfgNq46G` and `-XHAemd`, and a short list of long options. Anything else is refused.
6. **The target** goes through the same validator as the scanners ([section 4](#4-scope-and-target-validation)).

Checked here against the target `https://example.com`:

```
True  curl -sS https://example.com/        -> autorizado
False curl file:///data/secrets/APP_TOKEN  -> ... esquema 'file' não permitido
False curl -d @/data/x https://example.com -> ... lê arquivo local (@)
False curl http://127.0.0.1:8080/          -> ... URL para outro host ('127.0.0.1'), não o alvo
False nmap 169.254.169.254                 -> ... endereço numérico '169.254.169.254' não é o alvo
False nmap --script vuln example.com       -> flag '--script' recusada (...)
False curl -T /etc/passwd https://example.com -> ... opção -T do curl fora da lista permitida
False bash -c id                           -> binário 'bash' é proibido em qualquer fase (...)
```

**When it runs** (only with live execution on): with a hard timeout (60 s by default, 180 s at most), output cut at 8000 characters, and, in the local mode, a minimal environment (`PATH`, `HOME`, `LANG`, `LC_ALL`, `TZ`, `TMPDIR`), so the API's `APP_TOKEN`, `SESSION_SECRET` and encryption key do not reach a curl. `AGENT_EXECUTOR=auto` (default) uses the `cai-kali-toolbox` container through `docker exec` when it is running and reachable, and otherwise runs in the API's own process. The published stack has no Kali container, so in practice it is local.

**Audit.** The intent (`investigate.run`) is written before execution, and every decision, including every refusal, after (`investigate.commands`).

The leash is defense in depth, not a sandbox. Each review round found one more way for a scanner flag to read a file or leave the target. Turn live execution on only in an isolated environment.

## 7. Accounts, tokens and first run

- **Roles** (`orchestrator/domain/roles.py`): `viewer` reads; `auditor` reads plus the audit log; `operator` runs and deletes scans but neither reads the audit log nor manages users; `admin` has everything. An unknown role falls to `viewer`.
- **Credentials** (`orchestrator/api/deps.py`): the `APP_TOKEN` as the service admin; per-user tokens stored as a hash; OIDC Bearer sessions that re-read the user from the database on each request; the password login cookie (`rs_session`, `httpOnly`, `SameSite=Strict`), which also needs the `X-RoqueShield` header on writes. Sessions carry a version: logout, password change and deactivation end every session issued before. The last active admin cannot be deactivated or demoted.
- **`?token=`** is accepted only on the SSE route `/ui/api/events`, and only with the `APP_TOKEN`, so the token does not end up in logs or `Referer` headers.
- **Login throttle** (`orchestrator/auth/limite.py`): 5 failures per email+IP and 50 per IP across emails, then a wait that doubles from 30 s to 15 min. It lives in the API process memory, so a restart clears it; the audit entry `user.login_failed` is the record.
- **First run** (`orchestrator/api/routers/conta.py`): `POST /setup` creates the first admin only with the one-time code (`/data/secrets/SETUP_CODE`) or the `APP_TOKEN`, only while there are no users (then `410`), and serialized by a fixed-key row, so two concurrent setups do not create two admins. A wrong code goes through the same throttle as a wrong password (5 per origin, then `429` with `Retry-After`); before 0.5.1 each wrong attempt wrote an audit row with no limit. `install.sh` passes the code in the address fragment (`#setup=`), which the browser never sends to the server.
- **The API refuses to start** with the example `APP_TOKEN` unless `ALLOW_INSECURE_APP_TOKEN=true`.

## 8. The standalone container

The image `roqueos-shield:<version>-standalone` runs the API, the worker, Redis and ZAP in one container under a Python supervisor (`orchestrator/standalone/supervisor.py`), as UID 1000. `docker/compose.prod.yml` runs it with `cap_drop: [ALL]` and `no-new-privileges`.

- **Redis and ZAP listen only on `127.0.0.1`**, and both need a secret: Redis a password (the worker deserializes jobs, and ZAP in the same container processes hostile content), ZAP an API key, sent in the `X-ZAP-API-Key` header and never in a URL.
- **No secret on a command line.** The Redis password and, since 0.5.1, the ZAP key go in `0600` files under `/data/secrets` (`redis.conf`, `zap.properties`). On the command line they were readable by every process in the container through `/proc/<pid>/cmdline`, including the scanners.
- **Each process gets only the secrets it uses.** The worker, whose children are the scanners, does not get `APP_TOKEN`, `SESSION_SECRET`, `SETUP_CODE` or `REDIS_PASSWORD`. Redis and ZAP get none of the secrets in their environment. The worker keeps `SECRETS_KEY` (it decrypts the AI key), `ZAP_API_KEY`, `DATABASE_URL` and `REDIS_URL`, and the scanners inherit that environment.
- **The port.** `install.sh` publishes on `127.0.0.1`. Do the first run before publishing the port anywhere else, and put a TLS reverse proxy in front.

## 9. AI triage and the model gateway

- **Prompt injection.** A scanner can return evidence written to steer the model. What limits the damage: the scrubber removes the sensitive patterns before the model call (`orchestrator/ai/analyzer.py`); the triage output only adjusts severity and text, it does not execute anything; and the agent's commands go through the leash and, by default, are not executed.
- **Sovereignty.** When the primary model is local and fails, the fallback to a cloud provider sends the findings out, with the scrubber as the only barrier. `ALLOW_CLOUD_FALLBACK=false` forbids it. The default in `Settings` is `true`; `docker/compose.prod.yml` sets it to `false`. A regulated deployment should keep it `false`.
- **Model credentials.** `LLM_API_KEY` from the environment locks `LLM_API_BASE` too, so a request cannot redirect the key to another address.

## 10. The audit trail

Written by `orchestrator/audit/` for: `scan.create` (with `authorization_ref`), `scan.delete`, `target.create`, `finding.status_change`, `investigate.run` and `investigate.commands`, setting changes in `/settings/*` (secret values never logged), `setup.denied` and `setup.admin_created`, and the user events (`user.create`, `user.set_role`, `user.deactivate`, `user.set_password`, `user.rotate_token`, `user.login`, `user.login_failed`, `user.logout`).

**Append-only only on Postgres.** A trigger (migration 0004) refuses `UPDATE` and `DELETE` on `audit_log`. SQLite, the standalone's default database, has no such trigger. `REQUIRE_IMMUTABLE_AUDIT=true` makes the API refuse to start on SQLite; `docker/compose.prod.yml` sets it.

**Not audited:** the DefectDojo export (`POST /reports/{id}/export/defectdojo`), the OSINT exposure scan (`POST /exposure/scan`), and changes to `TARGET_ALLOWLIST` or `config/exposure_targets.yml` made in the environment or on disk rather than through `/settings/scope`.

## 11. Known limits

Not vulnerabilities, but the edges of what the controls do. If you find a way past one of them, report it ([SECURITY.md](../SECURITY.md)).

- **In the standalone image every process runs as the same user.** The API, the worker, ZAP and the scanners are UID 1000 and can read `/data/secrets` and the SQLite database. The per-process environment keeps the most valuable secrets out of the scanners' environment, but a compromised scanner is not isolated from the files. The compose stack (`docker/compose.prod.yml`) separates Postgres, Redis and ZAP into their own containers; the API and the workers still share an image and a user.
- **Scanners inherit `SECRETS_KEY`.** The worker needs it and the adapters do not pass a reduced environment to their subprocesses.
- **DNS is resolved more than once.** The scope check resolves when the target is created and when the scan is queued; the scanner resolves again later. Loopback and link-local are refused even for a name on the allowlist, but a name could still be re-pointed to another private address in between.
- **The scrubber is a list of patterns.** Anything not on it reaches the model (in triage) and the AI Fix Bundle evidence as written, including secrets found by the secret scanners.
- **The leash is not a sandbox** ([section 6](#6-the-ai-agent-and-its-command-leash)). In the local mode a command runs in the API's process space, as the API's user.
- **The login and setup throttle lives in memory** and resets with the container.
- **The Greenbone GMP connection is plain TCP** (`GREENBONE_PORT`, default 9390). Keep it on a private network.

## 12. Out of scope

- RoqueShield is not a WAF; blocking an active exploit is the target platform's job.
- It does not replace a manual pentest of critical applications.
- The AI triage is not forensic evidence: a person validates findings before acting on them.
- The DefectDojo export is not an authoritative compliance trail.
- Vulnerabilities in the upstream scanners themselves (nmap, ZAP, nuclei, trivy, semgrep): report them upstream.

## When something does not work

- A scan is refused with `target rejeitado pela policy` ("target refused by policy"): the target is outside the scope ([section 4](#4-scope-and-target-validation)). `POST /targets/check` says why; [OPERATIONS.md](OPERATIONS.md) explains how to allow a target.
- `POST /scans` answers `422 options.<scanner>.<field> não é aceito` ("is not accepted"): the option is not on the closed list ([section 5](#5-scanner-options)).
- The investigation answers `403` on `dry_run=false`: live execution is off, which is the default, or the caller is not an admin.
- The API does not start with `REQUIRE_IMMUTABLE_AUDIT=true`: the database is SQLite; use Postgres. Other startup failures are in [WHEN-IT-BREAKS.md](WHEN-IT-BREAKS.md).
