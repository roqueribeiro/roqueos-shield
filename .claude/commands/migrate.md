---
description: Roda alembic upgrade head (cria/atualiza schema do Postgres)
allowed-tools: Bash
argument-hint: ""
---

Aplique migrations alembic no Postgres:

```bash
make migrate
```

(É o mesmo que `docker compose --env-file .env --project-directory docker -f docker/compose.yml -f docker/compose.scanners.yml -f docker/compose.lab.yml run --rm --entrypoint alembic orchestrator upgrade head`.)

Após terminar, valide schema:

```bash
docker exec cai-postgres psql -U cai -d cai -c "\dt"
```

Se aparecer erro `relation already exists`: alguém criou tabelas via `init_db()` antes.
O reset abaixo **apaga todos os dados do banco, inclusive a trilha de auditoria**: mostre
ao usuário as tabelas e a contagem de linhas e só rode com confirmação explícita dele.

```bash
docker exec cai-postgres psql -U cai -d cai -c "DROP TABLE IF EXISTS findings, scans, audit_log, ai_runs, targets, alembic_version CASCADE;"
```

E rodar de novo. Reporte tabelas criadas.
