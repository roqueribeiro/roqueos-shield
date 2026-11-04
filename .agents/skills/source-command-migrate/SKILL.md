---
name: "source-command-migrate"
description: "Roda alembic upgrade head (cria/atualiza schema do Postgres)"
---

# source-command-migrate

Use this skill when the user asks to run the migrated source command `migrate`.

## Command Template

Aplique migrations alembic no Postgres:

```bash
docker compose --env-file .env -f docker/compose.yml -f docker/compose.scanners.yml -f docker/compose.lab.yml run --rm --entrypoint alembic orchestrator upgrade head
```

Após terminar, valide schema:

```bash
docker exec cai-postgres psql -U cai -d cai -c "\dt"
```

Se aparecer erro `relation already exists`: alguém criou tabelas via `init_db()` antes. Resetar:
```bash
docker exec cai-postgres psql -U cai -d cai -c "DROP TABLE IF EXISTS findings, scans, audit_log, ai_runs, targets, alembic_version CASCADE;"
```

E rodar de novo. Reporte tabelas criadas.
