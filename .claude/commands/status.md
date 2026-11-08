---
description: Diagnóstico rápido da stack, containers, DB, ZAP, AI gateway
allowed-tools: Bash
argument-hint: ""
---

Verifique saúde da stack em ordem rápida. Nenhum segredo vai para a linha de comando
nem para a tela: o token vai por arquivo de header (`curl -H @arquivo`), e o ZAP é
checado pelo healthcheck do container, não pela URL com `apikey=`.

```bash
echo "=== Containers ==="
docker compose --env-file .env --project-directory docker -f docker/compose.yml -f docker/compose.scanners.yml -f docker/compose.lab.yml ps

echo ""
echo "=== Orchestrator API ==="
curl -sf http://127.0.0.1:8080/health || echo "DOWN"
echo ""
H=$(mktemp) && chmod 600 "$H"
sed -n 's/^APP_TOKEN=\(.*\)/X-API-Token: \1/p' .env > "$H"
curl -sf http://127.0.0.1:8080/health/full -H @"$H" | jq 2>/dev/null || echo "health/full falhou"
rm -f "$H"

echo ""
echo "=== ZAP (healthcheck do container) ==="
docker inspect -f '{{.State.Health.Status}}' cai-zap 2>/dev/null || echo "cai-zap não existe"

echo ""
echo "=== Juice Shop ==="
curl -sf -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:3000

echo ""
echo "=== Postgres ==="
docker exec cai-postgres pg_isready -U cai -d cai 2>/dev/null
docker exec cai-postgres psql -U cai -d cai -c "SELECT 'targets' as t, count(*) FROM targets UNION ALL SELECT 'scans', count(*) FROM scans UNION ALL SELECT 'findings', count(*) FROM findings UNION ALL SELECT 'audit_log', count(*) FROM audit_log;" 2>/dev/null

echo ""
echo "=== Redis (arq queue) ==="
docker exec cai-redis redis-cli ping 2>/dev/null
docker exec cai-redis redis-cli LLEN arq:queue 2>/dev/null

echo ""
echo "=== AI keys (só se estão definidas, nunca o valor) ==="
grep -E '^(ANTHROPIC_API_KEY|OPENAI_API_KEY|LLM_API_BASE|LLM_MODEL)=' .env | sed -E 's/=.+$/=(definida)/; s/=$/=(vazia)/' 2>/dev/null
```

Sumarize em 5-7 linhas o que está UP, DOWN, o que falta. Sugira próximo passo de remediação se houver problema.
