---
name: "source-command-up"
description: "Sobe a stack CAI completa (orchestrator + worker + db + redis + scanners + lab)"
---

# source-command-up

Use this skill when the user asks to run the migrated source command `up`.

## Command Template

Suba a stack CAI completa. Profile padrão é `default + scanners + lab`.

```bash
docker compose --env-file .env -f docker/compose.yml -f docker/compose.scanners.yml -f docker/compose.lab.yml --profile default --profile scanners --profile lab up -d
```

Após subir, verifique se `cai-orchestrator`, `cai-postgres`, `cai-redis`, `cai-zap`, `cai-juice-shop` estão UP via `docker ps`. Reporte o resultado em uma linha.
