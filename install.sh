#!/bin/sh
# RoqueShield standalone in one command / em um comando:
#
#   curl -fsSL https://raw.githubusercontent.com/roqueribeiro/roqueos-shield/main/install.sh | sh
#
# Sobe o container, espera ele ficar saudável e abre a tela no navegador com o código
# de primeiro uso no endereço (no fragmento, que não vai ao servidor). Rodar de novo é
# seguro: se o container existe, ele só é religado (os dados ficam no volume).
#
# Variáveis opcionais / optional variables:
#   ROQUESHIELD_PORTA   porta no seu computador / port on your computer (8080)
#   ROQUESHIELD_VERSAO  versão da imagem / image version (a deste script / this script's)
#   ROQUESHIELD_NOME    nome do container e do volume / container and volume name (roqueshield)
#   ROQUESHIELD_NAO_ABRIR=1  não abre o navegador / do not open the browser
#
# O que ele NÃO faz: não publica a porta fora do seu computador (escuta em 127.0.0.1),
# não pede sudo, não instala o Docker e não mexe em nada fora do container e do volume.

set -eu

# A versão é fixa e conferida pelo gate de docs contra o pyproject (check_docs_fresh):
# o script de uma versão sobe a imagem daquela versão.
VERSAO_PADRAO="v0.5.0"

VERSAO="${ROQUESHIELD_VERSAO:-$VERSAO_PADRAO}"
PORTA="${ROQUESHIELD_PORTA:-8080}"
NOME="${ROQUESHIELD_NOME:-roqueshield}"
IMAGEM="roqueribeiro1988/roqueos-shield:${VERSAO}-standalone"
URL="http://localhost:${PORTA}"
MEMORIA_MIN_GB=6
SCRIPT_URL="https://raw.githubusercontent.com/roqueribeiro/roqueos-shield/main/install.sh"

case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in
  pt*) PT=1 ;;
  *) PT=0 ;;
esac
# tr_ "português" "english"
tr_() { if [ "$PT" = 1 ]; then printf '%s' "$1"; else printf '%s' "$2"; fi; }

if [ -t 1 ]; then
  N=$(printf '\033[1m'); V=$(printf '\033[32m'); A=$(printf '\033[33m'); E=$(printf '\033[31m'); R=$(printf '\033[0m')
else
  N=""; V=""; A=""; E=""; R=""
fi
passo() { printf '%s==>%s %s\n' "$N" "$R" "$*"; }
ok() { printf '    %s✓%s %s\n' "$V" "$R" "$*"; }
aviso() { printf '    %s!%s %s\n' "$A" "$R" "$*"; }
morre() { printf '\n%s%s%s %s\n' "$E" "$(tr_ 'Não deu:' 'Could not finish:')" "$R" "$*" >&2; exit 1; }

case "$PORTA" in
  *[!0-9]*|"") morre "$(tr_ "ROQUESHIELD_PORTA tem que ser um número (veio '$PORTA')." "ROQUESHIELD_PORTA must be a number (got '$PORTA').")" ;;
esac
case "$NOME" in
  *[!a-zA-Z0-9_.-]*|"") morre "$(tr_ 'ROQUESHIELD_NOME aceita só letras, números, ponto, hífen e sublinhado.' 'ROQUESHIELD_NOME accepts only letters, digits, dot, dash and underscore.')" ;;
esac

printf '\n%sRoqueShield%s %s\n\n' "$N" "$R" "$VERSAO"

# --- 1. Docker ---------------------------------------------------------------
passo "$(tr_ 'Conferindo o Docker' 'Checking Docker')"
command -v docker >/dev/null 2>&1 || morre "$(tr_ \
  'o Docker não está instalado. Instale o Docker Desktop (Mac e Windows) ou o Docker Engine (Linux): https://docs.docker.com/get-docker/ e rode este comando de novo.' \
  'Docker is not installed. Install Docker Desktop (Mac and Windows) or Docker Engine (Linux): https://docs.docker.com/get-docker/ and run this command again.')"
docker info >/dev/null 2>&1 || morre "$(tr_ \
  "o Docker está instalado mas não respondeu. Abra o Docker Desktop (ou 'sudo systemctl start docker' no Linux), espere ele terminar de iniciar e rode este comando de novo." \
  "Docker is installed but did not answer. Open Docker Desktop (or 'sudo systemctl start docker' on Linux), wait for it to finish starting and run this command again.")"
ok "$(tr_ 'Docker respondendo' 'Docker is up')"

# Os scanners (ZAP, nuclei) usam memória: com menos de 6 GB o kernel mata um deles no
# meio do scan, e o relatório sai com cobertura incompleta.
MEM_BYTES=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
case "$MEM_BYTES" in *[!0-9]*|"") MEM_BYTES=0 ;; esac
MEM_GB=$((MEM_BYTES / 1073741824))
if [ "$MEM_BYTES" -gt 0 ] && [ "$MEM_GB" -lt "$MEMORIA_MIN_GB" ]; then
  aviso "$(tr_ "o Docker tem ${MEM_GB} GB de memória; o RoqueShield pede ${MEMORIA_MIN_GB} GB." "Docker has ${MEM_GB} GB of memory; RoqueShield needs ${MEMORIA_MIN_GB} GB.")"
  aviso "$(tr_ 'No Docker Desktop: Settings > Resources > Memory. Dá para seguir, mas um scanner' 'In Docker Desktop: Settings > Resources > Memory. You can go on, but a scanner')"
  aviso "$(tr_ 'pode ser interrompido no meio e o scan sai com cobertura incompleta.' 'may be killed mid-scan and the scan ends with incomplete coverage.')"
else
  ok "$(tr_ "memória do Docker: ${MEM_GB} GB" "Docker memory: ${MEM_GB} GB")"
fi

# --- 2. Container ------------------------------------------------------------
existe=$(docker ps -a --filter "name=^/${NOME}\$" --format '{{.Names}}')
if [ -n "$existe" ]; then
  estado=$(docker inspect --format '{{.State.Status}}' "$NOME")
  imagem_atual=$(docker inspect --format '{{.Config.Image}}' "$NOME")
  if [ "$imagem_atual" != "$IMAGEM" ]; then
    aviso "$(tr_ "o container '$NOME' já existe com $imagem_atual (este script é de $IMAGEM)." "container '$NOME' already exists with $imagem_atual (this script is for $IMAGEM).")"
    aviso "$(tr_ 'Ele não é trocado sozinho. Para atualizar, mantendo os dados do volume:' 'It is not replaced on its own. To update, keeping the data in the volume:')"
    aviso "  docker rm -f $NOME  &&  curl -fsSL $SCRIPT_URL | sh"
  fi
  if [ "$estado" = "running" ]; then
    passo "$(tr_ "O container '$NOME' já está rodando" "Container '$NOME' is already running")"
  else
    passo "$(tr_ "Religando o container '$NOME'" "Starting container '$NOME' again")"
    docker start "$NOME" >/dev/null
  fi
  PORTA_REAL=$(docker port "$NOME" 8080/tcp 2>/dev/null | head -n 1 | sed 's/.*://')
  if [ -n "$PORTA_REAL" ] && [ "$PORTA_REAL" != "$PORTA" ]; then
    PORTA="$PORTA_REAL"
    URL="http://localhost:${PORTA}"
  fi
else
  passo "$(tr_ 'Baixando a imagem (cerca de 1,2 GB na primeira vez)' 'Downloading the image (about 1.2 GB the first time)')"
  if ! docker pull "$IMAGEM"; then
    docker image inspect "$IMAGEM" >/dev/null 2>&1 \
      || morre "$(tr_ "não consegui baixar $IMAGEM. Confira a internet e a versão." "could not download $IMAGEM. Check your connection and the version.")"
    aviso "$(tr_ 'não veio do registro; usando a imagem que já está neste computador.' 'not pulled from the registry; using the image already on this computer.')"
  fi
  passo "$(tr_ "Subindo o container '$NOME' em $URL" "Starting container '$NOME' on $URL")"
  # --add-host: no Linux, faz host.docker.internal apontar para o seu computador, como
  # no Docker Desktop. É por esse nome que o scan alcança um app rodando na sua máquina.
  if ! docker run -d --name "$NOME" \
    -p "127.0.0.1:${PORTA}:8080" \
    --shm-size=1g --stop-timeout 30 --restart unless-stopped \
    --add-host host.docker.internal:host-gateway \
    -v "${NOME}:/data" \
    "$IMAGEM" >/dev/null; then
    docker rm -f "$NOME" >/dev/null 2>&1 || true
    morre "$(tr_ "o container não subiu. Se a porta $PORTA está em uso, escolha outra:" "the container did not start. If port $PORTA is in use, pick another one:")
  curl -fsSL $SCRIPT_URL | ROQUESHIELD_PORTA=8081 sh"
  fi
fi

# --- 3. Saudável ---------------------------------------------------------------
passo "$(tr_ 'Esperando o RoqueShield ficar pronto' 'Waiting for RoqueShield to be ready')"
i=0
while :; do
  saude=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$NOME" 2>/dev/null || echo erro)
  [ "$saude" = "healthy" ] && break
  if [ "$saude" = "unhealthy" ] || [ "$(docker inspect --format '{{.State.Running}}' "$NOME" 2>/dev/null)" != "true" ]; then
    docker logs --tail 30 "$NOME" >&2 || true
    morre "$(tr_ 'o container não ficou saudável. As últimas linhas do log estão acima.' 'the container did not become healthy. The last log lines are above.')"
  fi
  i=$((i + 1))
  [ "$i" -gt 90 ] && morre "$(tr_ "passaram 3 minutos e ele não ficou pronto. Veja: docker logs $NOME" "3 minutes went by and it is not ready. See: docker logs $NOME")"
  sleep 2
done
ok "$(tr_ 'pronto' 'ready')"

# --- 4. Primeiro uso -----------------------------------------------------------
# O código vai no fragmento do endereço (#setup=...): o navegador não o manda ao
# servidor, a tela preenche o campo e apaga o código da barra. Ele não é impresso aqui.
ENDERECO="$URL"
precisa=$(docker exec "$NOME" python -c "import json,urllib.request as u;print(json.load(u.urlopen('http://127.0.0.1:8080/setup',timeout=5))['needs_setup'])" 2>/dev/null || echo "?")
if [ "$precisa" = "True" ]; then
  CODIGO=$(docker exec "$NOME" cat /data/secrets/SETUP_CODE 2>/dev/null || true)
  [ -n "$CODIGO" ] && ENDERECO="${URL}/#setup=${CODIGO}"
fi

abriu=0
if [ "${ROQUESHIELD_NAO_ABRIR:-}" = "" ]; then
  if [ "$(uname -s)" = "Darwin" ] && command -v open >/dev/null 2>&1; then
    open "$ENDERECO" >/dev/null 2>&1 && abriu=1
  elif command -v wslview >/dev/null 2>&1; then
    wslview "$ENDERECO" >/dev/null 2>&1 && abriu=1
  elif command -v xdg-open >/dev/null 2>&1 && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; }; then
    xdg-open "$ENDERECO" >/dev/null 2>&1 && abriu=1
  fi
fi

printf '\n%s%s%s%s ' "$N" "$V" "$(tr_ 'Pronto.' 'Done.')" "$R"
if [ "$abriu" = 1 ]; then
  tr_ "O navegador abriu em $URL" "Your browser opened $URL"
else
  tr_ "Abra $URL no navegador." "Open $URL in your browser."
fi
printf '\n'
if [ "$precisa" = "True" ]; then
  # A partir da 0.5.1 a tela aberta por aqui já vem com o código; antes dela, e quando
  # o navegador não abre sozinho, ele sai do comando abaixo.
  tr_ "  Crie a conta de administrador (e-mail e senha). Se a tela pedir o código de
  primeiro uso, ele sai de:  docker exec $NOME cat /data/secrets/SETUP_CODE
" "  Create the admin account (e-mail and password). If the screen asks for the
  first-run code, get it with:  docker exec $NOME cat /data/secrets/SETUP_CODE
"
fi
printf '\n'
tr_ "  Parar:         docker stop $NOME
  Ligar de novo: rode este mesmo comando (ou docker start $NOME)
  Desinstalar:   docker rm -f $NOME   (e docker volume rm $NOME para apagar os dados)

  Só teste o que você tem autorização para testar.
" "  Stop:          docker stop $NOME
  Start again:   run this same command (or docker start $NOME)
  Uninstall:     docker rm -f $NOME   (and docker volume rm $NOME to delete the data)

  Only test what you are authorized to test.
"
