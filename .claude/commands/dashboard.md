---
description: Sobe stack se preciso e mostra a URL do dashboard UI (sem imprimir o token)
allowed-tools: Bash
argument-hint: ""
---

```bash
# Se a stack não está no ar, sobe e migra
if ! docker ps --format '{{.Names}}' | grep -q '^cai-orchestrator$'; then
  echo "Subindo stack..."
  make up
  make migrate
fi

echo ""
echo "Dashboard CAI: http://127.0.0.1:8080/ui/"
echo "Cockpit de um scan: http://127.0.0.1:8080/ui/cockpit.html?scan_id=<id>"
echo "O token é o APP_TOKEN do .env (não é impresso aqui)."
```

Reporte a URL. O token não aparece em tela, nem na URL: segredo impresso fica no
histórico do terminal e no transcript. Diga ao usuário que ele cola o `APP_TOKEN` do
`.env` na tela de login.

Abas: Dashboard (visão geral, health), Scans (com link pro cockpit), AI Calls
(telemetria de cada chamada de LLM) e Logs (stream SSE do orchestrator).
