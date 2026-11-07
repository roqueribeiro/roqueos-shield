#!/usr/bin/env bash
# Sobe um shield descartável (uvicorn + SQLite novo, sem Redis) servindo a web já
# buildada em orchestrator/web_dist, e roda web/e2e/standalone.e2e.mjs contra ele.
#
#   (cd web && yarn build) && scripts/web_e2e.sh
#
# Os segredos e a senha do admin de teste são gerados aqui, ficam em arquivo 0600 numa
# pasta temporária e nunca vão para a tela. Sai com o código do e2e.
set -euo pipefail

raiz="$(cd "$(dirname "$0")/.." && pwd)"
porta="${E2E_PORTA:-8099}"
py="${PYTHON:-$raiz/.venv/bin/python}"
[ -x "$py" ] || py="$(command -v python)"

[ -f "$raiz/orchestrator/web_dist/index.html" ] || {
  echo "falta orchestrator/web_dist: rode (cd web && yarn build) antes" >&2
  exit 2
}

tmp="$(mktemp -d)"
pid=""
limpar() {
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  rm -rf "$tmp"
}
trap limpar EXIT

umask 077
export DATA_DIR="$tmp/data" DATABASE_URL="sqlite+aiosqlite:///$tmp/shield.db"
export REDIS_URL="redis://127.0.0.1:1/0" LOG_FORMAT=json
# O litellm, em modo DEV (o padrão), faz load_dotenv() do .env da pasta no import: o
# .env de quem desenvolve virava "ambiente do container" e travava o escopo inteiro na
# tela (medido em 07/11/2026). O e2e tem que ver o shield como ele sai na imagem.
export LITELLM_MODE=PRODUCTION
mkdir -p "$DATA_DIR"
(cd "$raiz" && "$py" -m orchestrator.standalone.segredos "$tmp/env" >/dev/null)
for f in "$tmp"/env/*; do export "$(basename "$f")=$(cat "$f")"; done
export E2E_SENHA="$("$py" -c 'import secrets; print(secrets.token_urlsafe(18))')"

# SQLite é o caminho do container único: o próprio app cria as tabelas no boot
# (o alembic só roda em Postgres, pelo supervisor).
(cd "$raiz" && exec "$py" -m uvicorn orchestrator.main:app --host 127.0.0.1 --port "$porta" --no-access-log) \
  >"$tmp/uvicorn.log" 2>&1 &
pid=$!

for _ in $(seq 1 60); do
  curl -fs "http://127.0.0.1:$porta/setup" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fs "http://127.0.0.1:$porta/setup" >/dev/null || {
  echo "o shield não subiu:" >&2
  tail -40 "$tmp/uvicorn.log" >&2
  exit 2
}

cd "$raiz/web"
SHIELD_URL="http://127.0.0.1:$porta" node e2e/standalone.e2e.mjs || {
  rc=$?
  echo "--- log do shield (fim) ---" >&2
  tail -30 "$tmp/uvicorn.log" >&2
  exit "$rc"
}
