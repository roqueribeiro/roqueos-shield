---
description: Gera AI Fix Bundle (JSON pra IA patcher) de um scan
allowed-tools: Bash Read
argument-hint: "<scan-id-uuid>"
---

Gera o AI Fix Bundle pra um scan já executado. JSON estruturado seguindo schema versionado (`schema_version: 1.0.0`) que outra IA (Claude Code, Cursor, Copilot, GPT) consome pra propor patches.

O entrypoint do orchestrator no compose é `uvicorn`; a CLI precisa do `--entrypoint python`.

```bash
SCAN_ID="$1"
docker compose --env-file .env --project-directory docker -f docker/compose.yml -f docker/compose.scanners.yml \
  run --rm --entrypoint python orchestrator -m orchestrator.cli bundle "$SCAN_ID"
```

Saída em `reports/scan-<id>/ai-bundle.json`.

Pra workflow completo (bundle + HANDOFF.md + snippet pra patcher), use o skill `cai-handoff-fix`.
