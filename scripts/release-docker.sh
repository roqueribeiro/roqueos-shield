#!/usr/bin/env bash
#
# Build e publicação das imagens do RoqueShield, na SUA máquina:
#   vX.Y.Z             o motor (orchestrator + worker), que o roqueos-server usa;
#   vX.Y.Z-standalone  o container único (motor + tela + Redis + ZAP), feito EM CIMA da
#                      vX.Y.Z recém-publicada, com as mesmas cinco travas.
#
# Até 23/10/2026 não havia caminho oficial: a roqueribeiro1988/roqueos-shield:latest
# de produção era de 29/08 e ninguém sabia dizer de qual commit. Este script é o
# caminho, e ele recusa o que faz uma imagem mentir:
#
#   1. A tag vX.Y.Z precisa existir, bater com o `version` do pyproject.toml e apontar
#      para o HEAD. É o que o /health e o relatório reportam.
#   2. Árvore suja vira imagem que não corresponde a commit nenhum.
#   3. Versão que já está no Hub não é republicada por cima.
#   4. O manifesto precisa ter amd64 e arm64 (servidores amd64, Macs com Apple Silicon arm64).
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

# 3. não republica (nenhuma das duas)
for t in "${TAG}" "${TAG}-standalone"; do
  if docker buildx imagetools inspect "${IMAGE}:${t}" >/dev/null 2>&1; then
    echo "ERRO: ${IMAGE}:${t} já existe no Docker Hub. Suba a versão no pyproject.toml." >&2
    exit 1
  fi
done

echo "==> builder buildx"
docker buildx inspect "${BUILDER}" >/dev/null 2>&1 ||
  docker buildx create --name "${BUILDER}" --driver docker-container
docker buildx inspect --bootstrap "${BUILDER}" >/dev/null

# As duas sobem primeiro como CANDIDATAS (`vX.Y.Z-candidato`): o Trivy roda nelas e só
# depois elas viram `vX.Y.Z` e `vX.Y.Z-standalone`. Antes, a tag final subia antes do
# Trivy, e uma imagem reprovada ficava pública com o nome que o install.sh baixa.
CAND="${TAG}-candidato"

echo "==> build multi-arch e push de ${IMAGE}:${CAND}"
docker buildx build --builder "${BUILDER}" \
  --platform linux/amd64,linux/arm64 \
  -f docker/images/orchestrator/Dockerfile \
  --label "org.opencontainers.image.version=${VERSAO}" \
  --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" \
  -t "${IMAGE}:${CAND}" \
  --push .

# 4. as duas arquiteturas
conferir_archs() {
ARCHS=$(docker buildx imagetools inspect "$1" --raw | python3 -c "
import json, sys
m = json.load(sys.stdin).get('manifests', [])
print(','.join(sorted({x['platform']['architecture'] for x in m
                       if x.get('platform', {}).get('architecture') not in (None, 'unknown')})))")
echo "    arquiteturas de $1: ${ARCHS}"
if [ "${ARCHS}" != "amd64,arm64" ]; then
  echo "ERRO: manifesto de $1 sem as duas arquiteturas (${ARCHS})." >&2
  exit 1
fi
}
conferir_archs "${IMAGE}:${CAND}"

# 5. Trivy, hard fail
trivy_hard() {
echo "==> Trivy (CRITICAL/HIGH com correção) em $1"
# As regras do semgrep e os templates do nuclei TÊM chave de exemplo (é assim que eles
# detectam segredo): o scanner de segredo fica fora só desses dois diretórios.
# .trivyignore.yaml: aceites com prazo, só para binário de scanner de terceiro.
TRIVY_ARGS=(--scanners vuln,secret --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1
  --skip-dirs /opt/nuclei-templates --skip-dirs /opt/semgrep-rules)
TRIVY_RC=0
if command -v trivy >/dev/null 2>&1; then
  trivy image "${TRIVY_ARGS[@]}" --ignorefile .trivyignore.yaml "$1" || TRIVY_RC=$?
else
  docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
    -v "${HOME}/.cache/trivy:/root/.cache/trivy" -v "$PWD/.trivyignore.yaml:/.trivyignore.yaml:ro" \
    aquasec/trivy:0.74.0 image "${TRIVY_ARGS[@]}" --ignorefile /.trivyignore.yaml \
    "$1" || TRIVY_RC=$?
fi
if [ "${TRIVY_RC}" != "0" ]; then
  echo "ERRO: Trivy reprovou $1. Só a candidata ficou no Hub; a tag final não foi criada." >&2
  exit 1
fi
}
trivy_hard "${IMAGE}:${CAND}"

echo "==> build multi-arch e push de ${IMAGE}:${CAND}-standalone (em cima de ${CAND})"
docker buildx build --builder "${BUILDER}" \
  --platform linux/amd64,linux/arm64 \
  -f docker/images/standalone/Dockerfile \
  --build-arg "ENGINE=${IMAGE}:${CAND}" \
  --label "org.opencontainers.image.version=${VERSAO}" \
  --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" \
  -t "${IMAGE}:${CAND}-standalone" \
  --push .
conferir_archs "${IMAGE}:${CAND}-standalone"
trivy_hard "${IMAGE}:${CAND}-standalone"

echo "==> as duas passaram: promovendo para ${TAG} e ${TAG}-standalone"
docker buildx imagetools create -t "${IMAGE}:${TAG}" "${IMAGE}:${CAND}"
docker buildx imagetools create -t "${IMAGE}:${TAG}-standalone" "${IMAGE}:${CAND}-standalone"
conferir_archs "${IMAGE}:${TAG}"
conferir_archs "${IMAGE}:${TAG}-standalone"

if [ "${MOVER_LATEST}" = "1" ]; then
  docker buildx imagetools create -t "${IMAGE}:latest" "${IMAGE}:${TAG}"
  echo "==> :latest -> ${TAG}"
fi

echo
echo "==> publicado: ${IMAGE}:${TAG} e ${IMAGE}:${TAG}-standalone (amd64 + arm64)"
echo "A frota recebe isto quando o roqueos-server fixar ${TAG} e cada servidor atualizar."
