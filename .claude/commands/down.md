---
description: Desce toda a stack CAI (sem apagar volumes)
allowed-tools: Bash
argument-hint: ""
---

Desça a stack CAI sem apagar volumes (use `make clean` se quiser apagar dados):

```bash
make down
```

O `make down` passa todos os arquivos de compose (base, scanners, lab, greenbone,
observability, agent, proxy) e todos os profiles, com `--env-file .env
--project-directory docker`. Compose só derruba serviço de arquivo que recebeu: com a
lista incompleta, Greenbone e Caddy sobreviviam ao down.

Reporte status ao final (`docker ps --filter name=cai-`).
