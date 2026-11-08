# Security Policy

RoqueShield is a security testing platform: it orchestrates active scanners (nmap, ZAP,
nuclei and others) against targets you choose. A flaw in it can have outsized impact,
such as scanning out of scope, reaching the container's own services or a cloud
metadata endpoint, leaking findings or secrets, or bypassing the PII scrubber before a
model call. We take reports seriously and prefer coordinated disclosure.

## Supported versions

RoqueShield is pre-1.0. Security fixes land on `main` and ship in the next release of
the image `roqueribeiro1988/roqueos-shield`. Only the latest released minor line gets
fixes.

| Version | Supported |
| --- | --- |
| latest `v0.5.x` (tags `v0.5.x` and `v0.5.x-standalone`) | yes |
| older tags | no, update with `install.sh --update` or the new tag |

## Reporting a vulnerability

**Do not open a public issue for a security report.**

Use [GitHub private vulnerability reporting](https://github.com/roqueribeiro/roqueos-shield/security/advisories/new).
It is private to the maintainers and has a coordinated-disclosure workflow built in.

Include, when you can:

- what the issue lets an attacker do, and from which position (no account, `viewer`,
  `operator`, `admin`, a scanned target, the network);
- the affected component (API route, scanner adapter, the standalone image, `install.sh`,
  the web UI in `web/`, the CLI or the MCP server);
- a minimal reproduction, ideally against a local lab target (OWASP Juice Shop in a
  container is enough);
- your suggested CVSS v3.1 vector (we will reassess);
- whether you want credit, and under what name.

## Scope

In scope:

- the `orchestrator/` package: API, adapters, the AI agent and its command leash, the
  scope validator, auth and sessions, audit log, scrubber, reporting;
- the images built from `docker/images/`, including the standalone image and its
  supervisor (`orchestrator/standalone/`);
- `install.sh` (the `curl | sh` installer);
- the web UI in `web/`, the `roqueshield` CLI and the MCP server (stdio and `POST /mcp`);
- the default `docker/compose.yml` and `docker/compose.prod.yml`.

Out of scope:

- vulnerabilities in the upstream scanners themselves (nmap, ZAP, nuclei, trivy,
  semgrep, ...): report those upstream;
- intentionally vulnerable lab targets (Juice Shop, DVWA, WebGoat);
- findings that RoqueShield produced against someone else's system: those belong to the
  system's owner;
- attacks that need a fully privileged local user or an already compromised host.

## Known limits (not vulnerabilities, but tell us if you find a way around them)

- In the standalone image every process (API, worker, ZAP, scanners) runs as the same
  user, which can read `/data/secrets`. The worker does not receive the service token,
  the session key or the first-run code, but it does keep the key that decrypts the
  stored AI key, the ZAP API key and the database and Redis URLs (with the Redis
  password), and the scanners it starts inherit that environment. A compromised
  scanner is not isolated from them.
- The scope check resolves DNS when a target is created and when a scan is enqueued;
  the scanner resolves again later. Loopback and link-local are refused even for a name
  on the allowlist, but a name could still be re-pointed to another private address.

## Our commitment

| Stage | Target |
| --- | --- |
| Acknowledgement | within 72 hours |
| Triage | within 7 days |
| Fix or mitigation | within 90 days, extendable by mutual agreement |
| Public disclosure | coordinated with you; by default 90 days after acknowledgement |

Unless you prefer otherwise, we credit you in [`CHANGELOG.md`](CHANGELOG.md) and in the
advisory.

## Safe harbor

We will not pursue legal action against researchers who make a good-faith effort to
follow this policy, avoid privacy violations, data destruction and service disruption,
do not exfiltrate more than needed to show impact, and give us a reasonable window
before public disclosure. If in doubt, ask first.

## Hardening guidance for operators

- Keep `LAB_ONLY=true` (the default). Put what you are authorized to test in
  `TARGET_ALLOWLIST` (or the **Scope** section). `LAB_ONLY=false` turns the private
  network guard off.
- Set `REQUIRE_AUTH_REF=true` to require an authorization reference on every scan.
- Do the first run before publishing the port, and never publish port 8080 as plain HTTP
  outside `127.0.0.1`: put a TLS reverse proxy in front.
- Treat a backup of `/data` as a secret: it holds the `APP_TOKEN` and the `SECRETS_KEY`.
- Give `operator` and `viewer` roles to people and CI; keep `admin` for who changes scope
  and AI settings.
- The AI agent's investigation only **plans** commands by default. Executing them
  (`dry_run=false`) needs `AGENT_LIVE_EXECUTION=true` and an admin. The command leash
  (allowed binaries, curl options, scope of every host, URL and path in the argv) is
  defense in depth, not a sandbox: turn live execution on only in an isolated
  environment.
- Read the threat model in [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md).
