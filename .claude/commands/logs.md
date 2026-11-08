---
description: Mostra os últimos logs do orchestrator (ou de um container específico)
allowed-tools: Bash
argument-hint: "[container-name]"
---

Mostre logs recentes. Se `$ARGUMENTS` vazio, default = `orchestrator`.

```bash
CONTAINER="${1:-orchestrator}"

# se for serviço do compose
docker compose --env-file .env --project-directory docker -f docker/compose.yml -f docker/compose.scanners.yml -f docker/compose.lab.yml logs --tail 100 $CONTAINER

# alternativamente direto
# docker logs cai-$CONTAINER --tail 100
```

Containers disponíveis: `orchestrator`, `worker`, `postgres`, `redis`, `zap`, `trivy`, `juice-shop`, `dvwa`, `webgoat`, `kali-toolbox`. O `ollama` só existe com `make ollama-up` (profile `ollama`): use `docker logs cai-ollama`.

Se `$ARGUMENTS` for `--all`, mostre todos os serviços ativos.

Sumarize qualquer ERROR ou WARN aparente nos logs e sugira próximo passo.
