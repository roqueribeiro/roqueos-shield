---
name: "source-command-down"
description: "Desce toda a stack CAI (sem apagar volumes)"
---

# source-command-down

Use this skill when the user asks to run the migrated source command `down`.

## Command Template

Desça a stack CAI sem apagar volumes (use `make clean` se quiser apagar dados):

```bash
docker compose --env-file .env -f docker/compose.yml -f docker/compose.scanners.yml -f docker/compose.lab.yml -f docker/compose.greenbone.yml -f docker/compose.observability.yml -f docker/compose.agent.yml --profile default --profile scanners --profile lab --profile greenbone --profile obs --profile ai-agent down
```

Reporte status ao final.
