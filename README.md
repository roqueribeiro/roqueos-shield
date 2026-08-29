# CAI — Continuous AI Security

> Vulnerability scanning + AI triage + AI Fix Bundle handoff to AI patchers (Claude Code, Cursor, Copilot).

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/release/python-3130/)
[![CI](https://github.com/roqueribeiro/more4cai/actions/workflows/ci.yml/badge.svg)](https://github.com/roqueribeiro/more4cai/actions/workflows/ci.yml)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#status)

**Documentation in other languages:** [Português (Brasil)](README.pt-BR.md)

---

CAI orchestrates **15 security scanners** behind one `ScannerAdapter` Protocol,
normalizes everything into a canonical `Finding` (CVSS v3, CWE, OWASP Top 10,
evidence), triages it with an LLM, and — when you ask it to — sends an **agent** to
confirm the finding by running real tools against the target, under a leash.

The four layers, in the order a scan goes through them:

| Layer | What it does | Where |
| --- | --- | --- |
| **1. Scan** | Runs the right tool for the target. **Semgrep** reads source code (SAST); Gitleaks/Trufflehog hunt secrets; Trivy covers CVEs in dependencies and images; Checkov covers IaC; ZAP and Nuclei probe the running app; Nmap and Greenbone cover the network. | `orchestrator/adapters/` |
| **2. Triage** | An LLM re-ranks severity, flags likely false positives, maps to OWASP, and proposes remediation — over evidence that a PII/PCI scrubber cleaned first. | `orchestrator/ai/analyzer.py` |
| **3. Investigate** | A ReAct agent picks a finding and tries to **confirm it**: it calls a real tool, reads the output, decides the next step, and closes with a verdict. Every command passes the executor's leash before it runs. | `orchestrator/ai/agentic/` |
| **4. Hand off** | An **AI Fix Bundle** (stable IDs, priority, location, tech-stack hints, verification steps) that another AI — Claude Code, Cursor, Copilot — consumes to propose the patch. | `orchestrator/reporting/exporters/` |

**The leash is the part that matters** if you plan to point this at anything real.
The agent's scope is not a sentence in a prompt — prompts do not constrain a process
with a shell. It is code in `agentic/executor.py`, checked before every command:
an allowlist per phase (recon vs. directed exploitation), a named deny list (brute
force, DoS, heavy fuzzing, shells), the target validated by the same validator the
scanners use, `argv` with no shell, refusal of shell metacharacters and of any flag
that writes to disk, hard timeouts, and a `dry_run` that plans without executing.
Twenty-seven mutation tests keep it honest, plus an end-to-end test that runs `nmap`
for real and confirms the forbidden command never reaches the executor.

The goal: **close the loop between scan and fix** for regulated environments —
banking, fintech, healthcare — where findings cannot leak to the public internet but
human pentesters cannot scale to every codebase. The stack is **self-hostable** and
the AI can run against a **local LLM** (LM Studio / Ollama), so vulnerability data
never has to leave your infrastructure. `ALLOW_CLOUD_FALLBACK=false` makes that a
rule instead of a hope: if the local model fails, the scan fails rather than sending
findings to a cloud provider.

> **RoqueShield** is CAI productized inside [RoqueOS](https://roqueos.com.br) — an admin-only, container-backed security app with a native desktop UI (live scan stepper over SSE, guided AI-provider config, one-click reports), an immutable audit trail, and AES-encrypted secrets. CAI is the engine; RoqueShield is the product surface. See [Architecture › Integração RoqueOS](docs/architecture.md#integração-roqueos-roqueshield).

## Status

CAI is **alpha (pre-1.0)**. Interfaces and DB schema may break. Production use against real assets is gated by compliance checks documented in [SECURITY.md](SECURITY.md) and the threat model in [docs/threat-model.md](docs/threat-model.md).

## How it works

```
   Operator                                AI Patcher
   (CLI / REST / UI)                       (Claude Code, Cursor, ...)
        |                                          ^
        v                                          |
   +-------------------+      +----------------+   |
   | CAI Orchestrator  |----->| Canonical      |   |
   |  - 15 adapters    |      | Finding (v2)   |   |
   |  - PII scrubber   |      +-------+--------+   |
   |  - litellm AI     |              v            |
   |    triage         |      +----------------+   |
   |  - Audit log      |----->| AI Triage      |   |
   |    (append-only)  |      | (OWASP/CWE)    |   |
   +---------+---------+      +-------+--------+   |
             |                        v            |
             |                +----------------+   |
             |                | AI Fix Bundle  |---+
             |                | JSON (1.0.0)   |
             |                +----------------+
             v
   +-------------------+
   | HTML reports +    |
   | Dashboard UI      |
   +-------------------+
```

## Quickstart (5 minutes)

Prerequisites: Docker Desktop (WSL2 on Windows) or Docker Engine, 8 GB of free RAM, optionally a Claude/OpenAI API key.

```bash
git clone https://github.com/roqueribeiro/more4cai.git
cd more4cai
cp .env.example .env
# fill in APP_TOKEN, POSTGRES_PASSWORD, ZAP_API_KEY (any random strings)
# optional: ANTHROPIC_API_KEY or OPENAI_API_KEY

make build       # build the orchestrator image
make up          # bring up postgres + redis + orchestrator + worker + zap + lab
make migrate     # alembic upgrade head
make smoke       # E2E: scan Juice Shop and produce an HTML report
```

Open `http://127.0.0.1:8080/ui/` to see the dashboard, or `http://127.0.0.1:8080/docs` for the OpenAPI spec. All endpoints require the `X-API-Token` header you set in `.env`.

## Features

- **15 scanner adapters** following a single `ScannerAdapter` Protocol — easy to add new ones (see [CONTRIBUTING.md](CONTRIBUTING.md) and [`orchestrator/adapters/base.py`](orchestrator/adapters/base.py)). Coverage spans web/DAST, network, CVE templates, containers, IaC, Kubernetes, secrets, and external attack surface (Shodan/Censys/GitHub/subdomain-takeover).
- **Canonical `Finding` schema** with deduplication, **CVSS v3 vector, CWE, OWASP Top 10**, evidence/PoC, confidence, references, and remediation hints — the structured data needed for compliance-mapped reporting.
- **Authorized-scope enforcement** — target allow-list, SSRF / private-network / loopback blocking, argv-injection guard, and an optional `REQUIRE_AUTH_REF` gate that ties every scan to a written authorization (`orchestrator/domain/target_validator.py`).
- **PII / PCI scrubber** that redacts CPF, CNPJ, card numbers, JWTs, AWS keys, and BR phone numbers _before_ anything leaves the orchestrator.
- **AI triage via [litellm](https://github.com/BerriAI/litellm)** — works with Anthropic, OpenAI, OpenRouter, Ollama, and LM Studio behind a single configuration. Local models keep sensitive findings on-prem.
- **AI Fix Bundle JSON exporter (schema 1.0.0)** — designed for handoff to an AI patcher that proposes code changes against the scanned project.
- **Append-only audit log** enforced at both the application and the Postgres trigger layer.
- **HTML technical and executive reports** + optional DefectDojo export.
- **Modular Docker Compose** — pick the profiles you need (`default`, `scanners`, `lab`, `greenbone`, `obs`, `proxy`, `ai-agent`).

## Adapters

| Adapter                      | Scanner                    | Type                         |
| ---------------------------- | -------------------------- | ---------------------------- |
| `semgrep_adapter`            | Semgrep                    | **SAST** — reads the source code |
| `nmap_adapter`               | Nmap                       | Network                      |
| `zap_adapter`                | OWASP ZAP                  | Web app (DAST)               |
| `nuclei_adapter`             | Nuclei                     | Templated vuln scan          |
| `trivy_adapter`              | Trivy                      | Container / IaC / FS         |
| `checkov_adapter`            | Checkov                    | IaC misconfig                |
| `gitleaks_adapter`           | Gitleaks                   | Secret scan                  |
| `trufflehog_adapter`         | Trufflehog                 | Verified-secret scan         |
| `dnstwist_adapter`           | dnstwist                   | Typosquatting / domain perms |
| `kube_bench_adapter`         | kube-bench                 | CIS Kubernetes               |
| `greenbone_adapter`          | Greenbone / OpenVAS        | Network vuln                 |
| `shodan_adapter`             | Shodan                     | Internet exposure (OSINT)    |
| `github_exposure_adapter`    | GitHub Search              | Code / secret leaks          |
| `censys_adapter`             | Censys                     | Internet exposure (optional) |
| `subdomain_takeover_adapter` | subfinder + httpx + nuclei | Subdomain takeover           |

## What keeps it honest

A broken scanner and a clean target produce **the same output: zero findings**. In a
report that goes to an auditor, that is the only difference that matters — so every
adapter must be able to tell the two apart.

| Situation | What the adapter does | What the report says |
| --- | --- | --- |
| Ran, found nothing | returns `[]` | no findings, coverage complete |
| Could not verify | raises `ScanIntegrityError` | listed in `scanners_skipped`, `coverage_complete: false` |
| Verified only in part | fills `RawResults.coverage_gaps` | an **INFO** finding naming the gap |

Two CI gates hold the two halves of that promise, and both were validated by mutation
testing — deliberately breaking the code and confirming the gate fails:

- **`silencio`** (`scripts/check_no_silence.py`) parses the adapters' AST and rejects
  an `except` in the scan lifecycle that ends in an empty result, a `poll()` that
  decides on `task.done()` without reading `task.result()`, and a fabricated
  success payload. An explicit `# silencio-ok: reason` is the only way past it.
- **`efetividade`** (`tests/integration/test_efetividade_e2e.py`) builds a repository
  with known flaws — command injection, tainted SQL, `pickle`, MD5, Flask `debug=True`,
  a public S3 bucket, a `0.0.0.0/0` security group, an unencrypted volume — runs the
  whole pipeline and requires real findings from every layer, while checking that a
  missing scanner shows up as skipped. Without it, a tool that only raised exceptions
  would pass every other test, because "zero findings" is the natural output of a
  broken scanner.

The full rule, with the nine historical cases that produced it, is in
[`.claude/rules/60-contrato-do-silencio.md`](.claude/rules/60-contrato-do-silencio.md)
(pt-BR) and [Architecture › O contrato do silêncio](docs/architecture.md).

### SAST works without egress

Semgrep's `--config auto` is incompatible with the `--metrics off` this project runs
for data sovereignty, and the `p/...` packs are downloaded from the registry on every
scan — which silently yields **zero rules** on a restricted corporate network. The
image therefore ships the `semgrep-rules` set (LGPL-2.1) at `/opt/semgrep-rules`,
pinned by commit and validated at build time, and the adapter loads only the language
directories present in the checkout. Point `SEMGREP_RULES_DIR` elsewhere to use your
own ruleset.

## Deeper documentation

The full project documentation is currently in **Portuguese (Brazil)**. Translation help is very welcome — see issues tagged `good first issue` + `docs`.

- [README.pt-BR.md](README.pt-BR.md) — full feature walkthrough (PT-BR)
- [docs/architecture.md](docs/architecture.md) — internal layout
- [docs/runbook.md](docs/runbook.md) — operations, troubleshooting, common pitfalls
- [docs/threat-model.md](docs/threat-model.md) — threat model and compliance gates
- [docs/usage.md](docs/usage.md) — end-to-end usage examples
- [docs/testing.md](docs/testing.md) — test strategy

## Contributing

Issues and PRs are welcome — please read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md) first. For security reports, follow [SECURITY.md](SECURITY.md) (private channel).

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

CAI bundles or invokes third-party software under their respective licenses; see `NOTICE` and `pyproject.toml`.
