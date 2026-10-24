#!/usr/bin/env bash
#
# Build e publicação da imagem do RoqueShield (orchestrator + worker), na SUA máquina.
#
# Até 23/10/2026 não havia caminho oficial: a roqueribeiro1988/roqueos-shield:latest
# de produção era de 29/08 e ninguém sabia dizer de qual commit. Este script é o
# caminho, e ele recusa o que faz uma imagem mentir:
#
#   1. A tag vX.Y.Z precisa existir, bater com o `version` do pyproject.toml e apontar
#      para o HEAD. É o que o /health e o relatório reportam.
#   2. Árvore suja vira imagem que não corresponde a commit nenhum.
#   3. Versão que já está no Hub não é republicada por cima.
#   4. O manifesto precisa ter amd64 e arm64 (acemagic é amd64, MacBook arm64).
#   5. Trivy com hard fail em CRITICAL/HIGH com correção.
#
# O roqueos-server fixa a versão da imagem (não usa :latest), então :latest só se move
# com --latest, para quem sobe o compose de dev à mão.
#
# Uso: scripts/release-docker.sh [--latest]
set -euo pipefail

IMAGE="roqueribeiro1988/roqueos-shield"
BUILDER="roqueos-shield-builder"
MOVER_LATEST=0
for arg in "$@"; do
  case "$arg" in
    --latest) MOVER_LATEST=1 ;;
    *) echo "uso: $0 [--latest]" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."

VERSAO=$(python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
TAG="v${VERSAO}"

# 1. tag existe e aponta para o HEAD
if ! git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
  echo "ERRO: a tag ${TAG} (pyproject.toml) não existe. Crie com: git tag ${TAG}" >&2
  exit 1
fi
if [ "$(git rev-list -n1 "${TAG}")" != "$(git rev-parse HEAD)" ]; then
  echo "ERRO: ${TAG} não aponta para o HEAD; a imagem não corresponderia à tag." >&2
  exit 1
fi

# 2. árvore limpa
if [ -n "$(git status --porcelain)" ]; then
  echo "ERRO: a árvore tem mudança não commitada." >&2
  exit 1
fi

# 3. não republica
if docker buildx imagetools inspect "${IMAGE}:${TAG}" >/dev/null 2>&1; then
  echo "ERRO: ${IMAGE}:${TAG} já existe no Docker Hub. Suba a versão no pyproject.toml." >&2
  exit 1
fi

echo "==> builder buildx"
docker buildx inspect "${BUILDER}" >/dev/null 2>&1 ||
  docker buildx create --name "${BUILDER}" --driver docker-container
docker buildx inspect --bootstrap "${BUILDER}" >/dev/null

echo "==> build multi-arch e push de ${IMAGE}:${TAG}"
docker buildx build --builder "${BUILDER}" \
  --platform linux/amd64,linux/arm64 \
  -f docker/images/orchestrator/Dockerfile \
  --label "org.opencontainers.image.version=${VERSAO}" \
  --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" \
  -t "${IMAGE}:${TAG}" \
  --push .

# 4. as duas arquiteturas
ARCHS=$(docker buildx imagetools inspect "${IMAGE}:${TAG}" --raw | python3 -c "
import json, sys
m = json.load(sys.stdin).get('manifests', [])
print(','.join(sorted({x['platform']['architecture'] for x in m
                       if x.get('platform', {}).get('architecture') not in (None, 'unknown')})))")
echo "    arquiteturas: ${ARCHS}"
if [ "${ARCHS}" != "amd64,arm64" ]; then
  echo "ERRO: manifesto sem as duas arquiteturas (${ARCHS})." >&2
  exit 1
fi

# 5. Trivy, hard fail
echo "==> Trivy (CRITICAL/HIGH com correção) em ${IMAGE}:${TAG}"
TRIVY_RC=0
if command -v trivy >/dev/null 2>&1; then
  trivy image --scanners vuln,secret --severity CRITICAL,HIGH --ignore-unfixed \
    --exit-code 1 "${IMAGE}:${TAG}" || TRIVY_RC=$?
else
  docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
    -v "${HOME}/.cache/trivy:/root/.cache/trivy" aquasec/trivy:0.74.0 image \
    --scanners vuln,secret --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1 \
    "${IMAGE}:${TAG}" || TRIVY_RC=$?
fi
if [ "${TRIVY_RC}" != "0" ]; then
  echo "ERRO: Trivy reprovou ${IMAGE}:${TAG}. A tag fica no Hub para diagnóstico;" >&2
  echo "  não aponte o roqueos-server para ela." >&2
  exit 1
fi

if [ "${MOVER_LATEST}" = "1" ]; then
  docker buildx imagetools create -t "${IMAGE}:latest" "${IMAGE}:${TAG}"
  echo "==> :latest -> ${TAG}"
fi

echo
echo "==> publicado: ${IMAGE}:${TAG} (amd64 + arm64)"
echo "A frota recebe isto quando o roqueos-server fixar ${TAG} e cada servidor atualizar."
