---
description: Backup do Postgres (inclui a trilha de auditoria) + reports
allowed-tools: Bash
argument-hint: ""
---

Roda o script de backup da stack de desenvolvimento:

```bash
make backup
```

O `scripts/backup.sh` gera em `backups/YYYYMMDD-HHMMSS/`:
- `cai.sql.gz`: `pg_dump` do `cai-postgres`. A trilha de auditoria (`audit_log`) é tabela dele e vai junto.
- `reports.tar.gz`: a pasta `reports/` inteira.

Não há alvo de restore: o dump é SQL puro, restaurar é dar ele ao `psql` num banco vazio.
O backup do container standalone é outro procedimento (docs/OPERATIONS.md, seção 3).

Reporte tamanho de cada artefato e caminho final.
