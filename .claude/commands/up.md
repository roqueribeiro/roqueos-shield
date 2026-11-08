---
description: Sobe a stack CAI completa (orchestrator + worker + db + redis + scanners + lab)
allowed-tools: Bash
argument-hint: ""
---

Suba a stack CAI. Profiles: `default + scanners + lab`. O Ollama local não sobe aqui
(profile `ollama`, pede GPU NVIDIA): se o usuário quiser, `make ollama-up`.

```bash
make up
```

(É o mesmo que `docker compose --env-file .env --project-directory docker -f docker/compose.yml -f docker/compose.scanners.yml -f docker/compose.lab.yml --profile default --profile scanners --profile lab up -d`.)

Após subir, verifique se `cai-orchestrator`, `cai-worker`, `cai-postgres`, `cai-redis`, `cai-zap`, `cai-juice-shop` estão UP via `docker ps`. O `cai-zap` leva um a dois minutos para ficar `healthy`. Reporte o resultado em uma linha.
