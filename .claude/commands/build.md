---
description: Build das imagens Docker (orchestrator obrigatório, kali-toolbox e cai-expert opcionais)
allowed-tools: Bash
argument-hint: "[orchestrator|kali|all]"
---

Execute o build apropriado conforme `$ARGUMENTS`. Toda chamada passa `--env-file .env`
e `--project-directory docker`: com `-f docker/...` o Compose procuraria o `.env` em
`docker/`, e no Compose v5 o `context: ..` resolveria a partir do lugar errado.

- Sem args ou `orchestrator`: só a imagem do orchestrator (que o worker também usa)
  ```bash
  docker compose --env-file .env --project-directory docker -f docker/compose.yml build orchestrator worker
  ```

- `kali`: kali-toolbox (lento, ~3GB de downloads, 15-30min)
  ```bash
  docker compose --env-file .env --project-directory docker -f docker/compose.yml -f docker/compose.scanners.yml build kali-toolbox
  ```

- `all`: o mesmo que `make build` (orchestrator + kali-toolbox + cai-expert opcional)
  ```bash
  make build
  ```

Reporte tamanho das imagens com `docker images | grep cai-` ao final.
