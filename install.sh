#!/bin/sh
# RoqueShield standalone in one command / em um comando:
#
#   curl -fsSL https://raw.githubusercontent.com/roqueribeiro/roqueos-shield/main/install.sh | sh
#
# Update to this script's version, keeping your data / Atualizar mantendo os dados:
#
#   curl -fsSL https://raw.githubusercontent.com/roqueribeiro/roqueos-shield/main/install.sh | sh -s -- --update
#
# It starts the container, waits until it is healthy and opens the browser with the
# first-run code in the address fragment, which never reaches the server. Running it
# again is safe: an existing container is only started again (data lives in a volume).
#
# Optional variables (English or Portuguese names):
#   ROQUESHIELD_PORT       / ROQUESHIELD_PORTA      port on your computer (8080)
#   ROQUESHIELD_VERSION    / ROQUESHIELD_VERSAO     image version (this script's)
#   ROQUESHIELD_NAME       / ROQUESHIELD_NOME       container and volume name (roqueshield)
#   ROQUESHIELD_NO_BROWSER / ROQUESHIELD_NAO_ABRIR  1, true or yes to not open the browser
#
# What it does NOT do: publish the port beyond your computer (it listens on 127.0.0.1),
# ask for sudo, install Docker, or touch anything outside its container and volume.
#
# Everything runs from main(), on the last line: if the download is cut halfway, sh
# has only received function definitions and nothing runs.

set -eu

# Pinned, and checked against pyproject.toml by scripts/check_docs_fresh.py: the script
# of a version installs the image of that version.
VERSAO_PADRAO="v0.5.1"
SCRIPT_URL="https://raw.githubusercontent.com/roqueribeiro/roqueos-shield/main/install.sh"
MEMORIA_MIN_MIB=5632 # 5.5 GiB: Docker Desktop reports a bit less than the 6 GB set

tr_() { if [ "$PT" = 1 ]; then printf '%s' "$1"; else printf '%s' "$2"; fi; }
passo() { printf '%s==>%s %s\n' "$N" "$R" "$*"; }
ok() { printf '    %s✓%s %s\n' "$V" "$R" "$*"; }
aviso() { printf '    %s!%s %s\n' "$A" "$R" "$*"; }
morre() { printf '\n%s%s%s %s\n' "$E" "$(tr_ 'Não deu:' 'Could not finish:')" "$R" "$*" >&2; exit 1; }

# The help comes from here and not from reading this file: under `curl | sh`, $0 is the
# shell, not the script, and there is no file to read.
ajuda() {
  cat <<'FIM'
RoqueShield standalone in one command / em um comando:

  curl -fsSL https://raw.githubusercontent.com/roqueribeiro/roqueos-shield/main/install.sh | sh

Update to this script's version, keeping your data / Atualizar mantendo os dados:

  curl -fsSL https://raw.githubusercontent.com/roqueribeiro/roqueos-shield/main/install.sh | sh -s -- --update

Options / Opções:
  --update       / --atualizar   replace the container with this script's version (data stays)
  --no-browser   / --nao-abrir   do not open the browser
  -h, --help                     this text

Optional variables (English or Portuguese names):
  ROQUESHIELD_PORT       / ROQUESHIELD_PORTA      port on your computer (8080)
  ROQUESHIELD_VERSION    / ROQUESHIELD_VERSAO     image version (this script's)
  ROQUESHIELD_NAME       / ROQUESHIELD_NOME       container and volume name (roqueshield)
  ROQUESHIELD_NO_BROWSER / ROQUESHIELD_NAO_ABRIR  1, true or yes to not open the browser

It listens on 127.0.0.1 only, does not ask for sudo, does not install Docker, and does
not touch anything outside its container and volume.
FIM
}

ligado() {
  case "$1" in
    1|[Tt][Rr][Uu][Ee]|[Yy][Ee][Ss]) return 0 ;;
    *) return 1 ;;
  esac
}

configurar() {
  case "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}" in
    pt*) PT=1 ;;
    *) PT=0 ;;
  esac
  if [ -t 1 ]; then
    N=$(printf '\033[1m'); V=$(printf '\033[32m'); A=$(printf '\033[33m'); E=$(printf '\033[31m'); R=$(printf '\033[0m')
  else
    N=""; V=""; A=""; E=""; R=""
  fi

  VERSAO="${ROQUESHIELD_VERSION:-${ROQUESHIELD_VERSAO:-$VERSAO_PADRAO}}"
  PORTA="${ROQUESHIELD_PORT:-${ROQUESHIELD_PORTA:-8080}}"
  NOME="${ROQUESHIELD_NAME:-${ROQUESHIELD_NOME:-roqueshield}}"
  # Only 1/true/yes turn it on: before, any non-empty value did, so
  # ROQUESHIELD_NO_BROWSER=0 or =false kept the browser closed.
  pedido_nao_abrir="${ROQUESHIELD_NO_BROWSER:-${ROQUESHIELD_NAO_ABRIR:-}}"
  if ligado "$pedido_nao_abrir"; then
    NAO_ABRIR=1
  else
    NAO_ABRIR=0
    case "$pedido_nao_abrir" in
      ""|0|[Ff][Aa][Ll][Ss][Ee]|[Nn][Oo]) ;;
      *) aviso "$(tr_ "ROQUESHIELD_NO_BROWSER='$pedido_nao_abrir' não é 1/true/yes; o navegador vai abrir." "ROQUESHIELD_NO_BROWSER='$pedido_nao_abrir' is not 1/true/yes; the browser will open.")" ;;
    esac
  fi
  ATUALIZAR=0
  for arg in "$@"; do
    case "$arg" in
      --update|--atualizar) ATUALIZAR=1 ;;
      --no-browser|--nao-abrir) NAO_ABRIR=1 ;;
      -h|--help) ajuda; exit 0 ;;
      *) morre "$(tr_ "opção desconhecida: $arg (use --update ou --no-browser)" "unknown option: $arg (use --update or --no-browser)")" ;;
    esac
  done

  case "$PORTA" in
    *[!0-9]*|"") morre "$(tr_ "a porta tem que ser um número (veio '$PORTA')." "the port must be a number (got '$PORTA').")" ;;
  esac
  if [ "$PORTA" -lt 1 ] || [ "$PORTA" -gt 65535 ]; then
    morre "$(tr_ "a porta tem que estar entre 1 e 65535 (veio $PORTA)." "the port must be between 1 and 65535 (got $PORTA).")"
  fi
  case "$NOME" in
    [!a-zA-Z0-9]*|*[!a-zA-Z0-9_.-]*|"") morre "$(tr_ 'o nome aceita só letras, números, ponto, hífen e sublinhado, começando por letra ou número.' 'the name accepts only letters, digits, dot, dash and underscore, starting with a letter or digit.')" ;;
  esac
  case "$VERSAO" in
    *[!a-zA-Z0-9_.-]*|"") morre "$(tr_ "versão inválida: '$VERSAO'." "invalid version: '$VERSAO'.")" ;;
  esac
  IMAGEM="roqueribeiro1988/roqueos-shield:${VERSAO}-standalone"
  URL="http://localhost:${PORTA}"
}

conferir_docker() {
  passo "$(tr_ 'Conferindo o Docker' 'Checking Docker')"
  command -v docker >/dev/null 2>&1 || morre "$(tr_ \
    'o Docker não está instalado. Instale o Docker Desktop (Mac e Windows) ou o Docker Engine (Linux): https://docs.docker.com/get-docker/ e rode este comando de novo.' \
    'Docker is not installed. Install Docker Desktop (Mac and Windows) or Docker Engine (Linux): https://docs.docker.com/get-docker/ and run this command again.')"
  if ! erro_docker=$(docker info 2>&1 >/dev/null); then
    case "$erro_docker" in
      *ermission\ denied*)
        morre "$(tr_ \
          "seu usuário não tem permissão no Docker. No Linux: sudo usermod -aG docker \$USER, saia e entre de novo na sessão, e rode este comando outra vez." \
          "your user has no permission to use Docker. On Linux: sudo usermod -aG docker \$USER, log out and back in, and run this command again.")" ;;
      *)
        morre "$(tr_ \
          "o Docker está instalado mas não respondeu. Abra o Docker Desktop (ou 'sudo systemctl start docker' no Linux), espere ele terminar de iniciar e rode este comando de novo." \
          "Docker is installed but did not answer. Open Docker Desktop (or 'sudo systemctl start docker' on Linux), wait for it to finish starting and run this command again.")" ;;
    esac
  fi
  ok "$(tr_ 'Docker respondendo' 'Docker is up')"

  # ZAP and nuclei need memory: below ~6 GB the kernel kills one of them mid-scan and
  # the report comes out with incomplete coverage.
  mem=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  case "$mem" in *[!0-9]*|"") mem=0 ;; esac
  mib=$((mem / 1048576))
  if [ "$mib" -eq 0 ]; then
    aviso "$(tr_ 'não consegui medir a memória do Docker; o RoqueShield pede 6 GB.' 'could not measure Docker memory; RoqueShield needs 6 GB.')"
  elif [ "$mib" -lt "$MEMORIA_MIN_MIB" ]; then
    gb=$(( (mib + 512) / 1024 ))
    aviso "$(tr_ "o Docker tem cerca de ${gb} GB de memória; o RoqueShield pede 6 GB." "Docker has about ${gb} GB of memory; RoqueShield needs 6 GB.")"
    aviso "$(tr_ 'No Docker Desktop: Settings > Resources > Memory. Dá para seguir, mas um scanner' 'In Docker Desktop: Settings > Resources > Memory. You can go on, but a scanner')"
    aviso "$(tr_ 'pode ser interrompido no meio e o scan sai com cobertura incompleta.' 'may be killed mid-scan and the scan ends with incomplete coverage.')"
  else
    ok "$(tr_ "memória do Docker: $(( (mib + 512) / 1024 )) GB" "Docker memory: $(( (mib + 512) / 1024 )) GB")"
  fi
}

baixar_imagem() {
  passo "$(tr_ 'Baixando a imagem (cerca de 1,2 GB na primeira vez)' 'Downloading the image (about 1.2 GB the first time)')"
  if ! docker pull "$IMAGEM"; then
    docker image inspect "$IMAGEM" >/dev/null 2>&1 \
      || morre "$(tr_ "não consegui baixar $IMAGEM. Confira a internet e a versão." "could not download $IMAGEM. Check your connection and the version.")"
    aviso "$(tr_ 'não veio do registro; usando a imagem que já está neste computador.' 'not pulled from the registry; using the image already on this computer.')"
  fi
}

criar_container() {
  passo "$(tr_ "Subindo o container '$NOME' em $URL" "Starting container '$NOME' on $URL")"
  # --add-host: on Linux, makes host.docker.internal point at your computer, as Docker
  # Desktop does. That is how a scan reaches an app running on your machine.
  if ! docker run -d --name "$NOME" \
    -p "127.0.0.1:${PORTA}:8080" \
    --shm-size=1g --stop-timeout 30 --restart unless-stopped \
    --add-host host.docker.internal:host-gateway \
    -v "${NOME}:/data" \
    "$IMAGEM" >/dev/null; then
    docker rm -f "$NOME" >/dev/null 2>&1 || true
    morre "$(tr_ "o container não subiu. Se a porta $PORTA está em uso, escolha outra:" "the container did not start. If port $PORTA is in use, pick another one:")
  curl -fsSL $SCRIPT_URL | ROQUESHIELD_PORT=8081 sh"
  fi
}

container() {
  if docker container inspect "$NOME" >/dev/null 2>&1; then
    estado=$(docker inspect --format '{{.State.Status}}' "$NOME")
    imagem_atual=$(docker inspect --format '{{.Config.Image}}' "$NOME")
    if [ "$ATUALIZAR" = 1 ] && [ "$imagem_atual" != "$IMAGEM" ]; then
      baixar_imagem
      passo "$(tr_ "Atualizando '$NOME': $imagem_atual -> $IMAGEM (o volume com os dados fica)" "Updating '$NOME': $imagem_atual -> $IMAGEM (the data volume stays)")"
      PORTA_REAL=$(docker port "$NOME" 8080/tcp 2>/dev/null | head -n 1 | sed 's/.*://')
      [ -n "$PORTA_REAL" ] && PORTA="$PORTA_REAL" && URL="http://localhost:${PORTA}"
      docker rm -f "$NOME" >/dev/null
      criar_container
      return
    fi
    if [ "$imagem_atual" != "$IMAGEM" ]; then
      aviso "$(tr_ "o container '$NOME' é de $imagem_atual (este script instala $IMAGEM)." "container '$NOME' runs $imagem_atual (this script installs $IMAGEM).")"
      aviso "$(tr_ 'Para atualizar, mantendo os dados:' 'To update, keeping your data:')"
      aviso "  curl -fsSL $SCRIPT_URL | sh -s -- --update"
    fi
    case "$estado" in
      running) passo "$(tr_ "O container '$NOME' já está rodando" "Container '$NOME' is already running")" ;;
      paused) passo "$(tr_ "Retomando o container '$NOME'" "Resuming container '$NOME'")"; docker unpause "$NOME" >/dev/null ;;
      *) passo "$(tr_ "Religando o container '$NOME'" "Starting container '$NOME' again")"; docker start "$NOME" >/dev/null ;;
    esac
    PORTA_REAL=$(docker port "$NOME" 8080/tcp 2>/dev/null | head -n 1 | sed 's/.*://')
    if [ -n "$PORTA_REAL" ] && [ "$PORTA_REAL" != "$PORTA" ]; then
      PORTA="$PORTA_REAL"
      URL="http://localhost:${PORTA}"
    fi
  else
    baixar_imagem
    criar_container
  fi
}

esperar_pronto() {
  passo "$(tr_ 'Esperando o RoqueShield ficar pronto' 'Waiting for RoqueShield to be ready')"
  i=0
  while :; do
    saude=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$NOME" 2>/dev/null || echo erro)
    [ "$saude" = "healthy" ] && break
    if [ "$saude" = "none" ] && docker exec "$NOME" python -c "import urllib.request as u;u.urlopen('http://127.0.0.1:8080/health',timeout=3)" >/dev/null 2>&1; then
      break
    fi
    if [ "$saude" = "unhealthy" ] || [ "$(docker inspect --format '{{.State.Running}}' "$NOME" 2>/dev/null)" != "true" ]; then
      docker logs --tail 30 "$NOME" >&2 || true
      morre "$(tr_ 'o container não ficou saudável. As últimas linhas do log estão acima.' 'the container did not become healthy. The last log lines are above.')"
    fi
    i=$((i + 1))
    [ "$i" -gt 90 ] && morre "$(tr_ "passaram 3 minutos e ele não ficou pronto. Veja: docker logs $NOME" "3 minutes went by and it is not ready. See: docker logs $NOME")"
    sleep 2
  done
  ok "$(tr_ 'pronto' 'ready')"
}

abrir_com() {
  if [ "$(uname -s)" = "Darwin" ] && command -v open >/dev/null 2>&1; then
    open "$1" >/dev/null 2>&1
  elif grep -qi microsoft /proc/version 2>/dev/null; then
    if command -v wslview >/dev/null 2>&1; then
      wslview "$1" >/dev/null 2>&1
    elif command -v explorer.exe >/dev/null 2>&1; then
      # explorer.exe returns 1 even when it opens; a Linux path needs translating.
      alvo="$1"
      [ -e "$1" ] && command -v wslpath >/dev/null 2>&1 && alvo=$(wslpath -w "$1")
      explorer.exe "$alvo" >/dev/null 2>&1 || true
    else
      return 1
    fi
  elif command -v xdg-open >/dev/null 2>&1 && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; }; then
    xdg-open "$1" >/dev/null 2>&1
  else
    return 1
  fi
}

primeiro_uso() {
  # The code goes in the address fragment (#setup=...): the browser never sends it to
  # the server, and the screen fills the field and removes it from the address bar. It
  # is not printed here, and not passed on the browser's command line either (process
  # arguments show up in `ps` for every user of the machine): it goes in a local page,
  # in a folder only you can read, which is deleted after five minutes.
  precisa=$(docker exec "$NOME" python -c "import json,urllib.request as u;print(json.load(u.urlopen('http://127.0.0.1:8080/setup',timeout=5))['needs_setup'])" 2>/dev/null || echo "?")
  codigo=""
  if [ "$precisa" = "True" ]; then
    codigo=$(docker exec "$NOME" cat /data/secrets/SETUP_CODE 2>/dev/null || true)
    case "$codigo" in *[!A-Za-z0-9_-]*) codigo="" ;; esac
  fi

  abriu=0
  if [ "$NAO_ABRIR" != 1 ]; then
    if [ -z "$codigo" ]; then
      abrir_com "$URL" && abriu=1
    else
      # Snap browsers (Ubuntu) do not see /tmp nor hidden folders in $HOME.
      if [ "$(uname -s)" = "Darwin" ]; then base="${TMPDIR:-/tmp}"; else base="$HOME"; fi
      pasta=$(umask 077 && mktemp -d "$base/roqueshield-abrir.XXXXXX") || pasta=""
      if [ -n "$pasta" ]; then
        (
          umask 077
          printf '<!doctype html><meta charset="utf-8"><title>RoqueShield</title>'
          printf '<script>location.replace("%s/#setup=%s")</script>' "$URL" "$codigo"
          printf '<a href="%s/#setup=%s">RoqueShield</a>\n' "$URL" "$codigo"
        ) >"$pasta/abrir.html"
        chmod 600 "$pasta/abrir.html"
        abrir_com "$pasta/abrir.html" && abriu=1
        (sleep 300; rm -rf "$pasta") >/dev/null 2>&1 &
      fi
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
    if [ "$abriu" = 1 ]; then
      tr_ "  Crie a conta de administrador: e-mail e senha. Se a tela pedir o código de
  primeiro uso, ele sai de:  docker exec $NOME cat /data/secrets/SETUP_CODE
" "  Create the admin account: e-mail and password. If the screen asks for the
  first-run code, get it with:  docker exec $NOME cat /data/secrets/SETUP_CODE
"
    else
      tr_ "  Crie a conta de administrador. O código de primeiro uso sai de:
    docker exec $NOME cat /data/secrets/SETUP_CODE
" "  Create the admin account. Get the first-run code with:
    docker exec $NOME cat /data/secrets/SETUP_CODE
"
    fi
  fi
  printf '\n'
  tr_ "  Parar:         docker stop $NOME
  Ligar de novo: rode este mesmo comando (ou docker start $NOME)
  Atualizar:     curl -fsSL $SCRIPT_URL | sh -s -- --update
  Desinstalar:   docker rm -f $NOME   (e docker volume rm $NOME para apagar os dados)

  Só teste o que você tem autorização para testar.
" "  Stop:          docker stop $NOME
  Start again:   run this same command (or docker start $NOME)
  Update:        curl -fsSL $SCRIPT_URL | sh -s -- --update
  Uninstall:     docker rm -f $NOME   (and docker volume rm $NOME to delete the data)

  Only test what you are authorized to test.
"
}

main() {
  configurar "$@"
  printf '\n%sRoqueShield%s %s\n\n' "$N" "$R" "$VERSAO"
  conferir_docker
  container
  esperar_pronto
  primeiro_uso
}

main "$@"
