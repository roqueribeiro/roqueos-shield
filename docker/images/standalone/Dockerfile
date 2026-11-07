# syntax=docker/dockerfile:1.7
#
# RoqueShield standalone: o motor (orchestrator + worker + scanners), a tela, o
# Redis e o ZAP num container só. Decisão do founder em 06/11/2026: um `docker run`
# faz tudo, inclusive o scan de aplicação web.
#
#   docker run -d --name roqueshield -p 8080:8080 --shm-size=1g \
#     -v roqueshield:/data roqueribeiro1988/roqueos-shield:<versão>-standalone
#
# Construída POR CIMA da imagem do motor (a mesma que o RoqueOS usa), para as duas
# nunca divergirem em scanner, regra ou versão. O RoqueOS continua usando o motor
# sozinho; nada aqui muda o que ele roda.
#
# Build (scripts/release-docker.sh faz os dois):
#   docker build -f docker/images/orchestrator/Dockerfile -t roqueos-shield-engine:local .
#   docker build -f docker/images/standalone/Dockerfile --build-arg ENGINE=roqueos-shield-engine:local .

ARG ENGINE=roqueos-shield-engine:local

# --- a tela (web/) -------------------------------------------------------------
FROM node:22.20.0-bookworm-slim AS web
WORKDIR /src/web
COPY web/package.json web/yarn.lock ./
RUN yarn install --frozen-lockfile --ignore-scripts --network-timeout 600000
COPY web/ ./
RUN yarn quasar prepare >/dev/null && yarn quasar build \
    && test -f /src/orchestrator/web_dist/index.html

# --- o ZAP, da imagem oficial, fixada por digest --------------------------------
FROM zaproxy/zap-stable@sha256:781a2bdaea47324e7bab583e2263f21d257b0aee61ed51521a5be45f5f5081ef AS zap

# --- o container final -----------------------------------------------------------
FROM ${ENGINE}
USER root
# redis-server: a fila do worker, só em 127.0.0.1.
# openjdk + firefox-esr: o ZAP e o navegador do AJAX spider (o que acha rota de SPA).
RUN apt-get update \
    && apt-get install -y --no-install-recommends redis-server openjdk-21-jre-headless firefox-esr \
    && rm -rf /var/lib/apt/lists/* \
    && redis-server --version && java -version 2>&1 | head -1 && firefox-esr --version
COPY --from=zap /zap /opt/zap
# Invólucro e não symlink: o zap.sh acha o próprio diretório pelo caminho chamado.
RUN printf '#!/bin/sh\nexec /opt/zap/zap.sh "$@"\n' > /usr/local/bin/zap.sh \
    && chmod 0755 /usr/local/bin/zap.sh \
    && test -x /opt/zap/zap.sh
COPY --from=web /src/orchestrator/web_dist /app/orchestrator/web_dist
RUN mkdir -p /data && chown 1000:1000 /data
ENV DATA_DIR=/data \
    HOME=/data
USER 1000
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]
ENTRYPOINT ["python", "-m", "orchestrator.standalone.supervisor"]
