# CAI orchestrator — comprehensive image.
#
# Bundles the heavy scanner CLIs (nuclei / gitleaks / trufflehog / trivy) + Python
# scanners (dnstwist / checkov / semgrep) + o ruleset OFFLINE do semgrep, na
# imagem do orchestrator+worker, para que os
# adapters run them as in-process subprocesses (no docker.sock, no kali-toolbox
# sidecar for the core scan set). This is the image RoqueOS (RoqueShield)
# publishes + runs as a single shared stack.
#
# amd64-first (the binaries below pull linux_amd64 releases — the RoqueOS demo is
# amd64). For arm64, swap the *_amd64 / _x64 release assets for their arm64
# equivalents.

# ---- scanner CLIs (download once, copy into the final image) ----------------
FROM debian:bookworm-slim AS tools
ARG NUCLEI_VERSION=3.3.7
ARG GITLEAKS_VERSION=8.21.2
ARG TRUFFLEHOG_VERSION=3.82.13
# 0.58.1 nao baixa mais: o asset trivy_0.58.1_Linux-64bit.tar.gz devolve 404, e o
# mesmo vale para 0.58.2, 0.59.1 e 0.60.0 -- a aquasecurity podou os binarios das
# releases antigas. Medido em 2026-08-29: das cinco versoes testadas so a atual
# responde 200. Um pin de release do GitHub nao e imutavel como um digest de
# imagem; se este 404 voltar, e subir a versao de novo, nao vendorizar o binario.
ARG TRIVY_VERSION=0.74.0
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tools
RUN set -eux; \
    curl -fsSL -o nuclei.zip "https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VERSION}/nuclei_${NUCLEI_VERSION}_linux_amd64.zip" \
    && unzip -o nuclei.zip nuclei -d /usr/local/bin && rm nuclei.zip; \
    curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" | tar -xz -C /usr/local/bin gitleaks; \
    curl -fsSL "https://github.com/trufflesecurity/trufflehog/releases/download/v${TRUFFLEHOG_VERSION}/trufflehog_${TRUFFLEHOG_VERSION}_linux_amd64.tar.gz" | tar -xz -C /usr/local/bin trufflehog; \
    curl -fsSL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" | tar -xz -C /usr/local/bin trivy; \
    chmod +x /usr/local/bin/nuclei /usr/local/bin/gitleaks /usr/local/bin/trufflehog /usr/local/bin/trivy

# ---- ruleset do Semgrep, embarcado e validado no build ----------------------
# POR QUE EMBARCAR: o default `--config p/security-audit` baixa as regras do
# registry da Semgrep a cada scan. Num banco a rede e restrita, e sem alcancar o
# registry o semgrep sai com codigo 0, ZERO regras e zero achados -- o silencio
# classico. Com o ruleset em disco, ~1000 regras rodam OFFLINE.
#
# So os diretorios por linguagem, validados um a um: a RAIZ do repo tem config
# invalida e passar a raiz faz o semgrep abortar com "1 configs were invalid" e
# zero regras (medido). O `--validate` abaixo e um gate de BUILD: se um diretorio
# quebrar numa atualizacao do pin, a imagem nao sai.
# elixir fica de fora: exige extensao proprietaria que nao vem no open source.
FROM python:3.13-slim AS rules
ARG SEMGREP_RULES_COMMIT=40b8c63f75dc7c22c8a77482d73bfb864b146f7e
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "semgrep>=1.100.0"
RUN set -eux; \
    git init -q /src && cd /src \
    && git remote add origin https://github.com/semgrep/semgrep-rules.git \
    && git fetch -q --depth 1 origin "${SEMGREP_RULES_COMMIT}" \
    && git checkout -q FETCH_HEAD; \
    mkdir -p /opt/semgrep-rules; \
    for d in python javascript typescript java go ruby php csharp terraform \
             dockerfile bash rust kotlin swift scala yaml json html c ocaml \
             clojure generic; do \
        cp -r "/src/$d" /opt/semgrep-rules/; \
    done; \
    find /opt/semgrep-rules -type d -name .semgrep_logs -prune -exec rm -rf {} +; \
    cd /; rm -rf /src; \
    # O `cd /` acima nao e enfeite: o RUN faz `cd /src` no comeco, e apagar /src
    # deixava o processo com um cwd inexistente. O semgrep seguinte morria em
    # Semgrep_envvars.of_current_sys_env com Sys_error("No such file or
    # directory") -- erro que nao diz nada sobre diretorio apagado, e que so
    # aparece no `docker build` inteiro.
    for d in /opt/semgrep-rules/*/; do \
        semgrep --validate --config "$d" --metrics off --disable-version-check; \
    done; \
    echo "${SEMGREP_RULES_COMMIT}" > /opt/semgrep-rules/PINNED_COMMIT

# ---- templates do nuclei, embarcados e CONFERIDOS no build ------------------
# Mesma logica do ruleset do semgrep, e pela mesma razao: o binario do nuclei era
# instalado e os TEMPLATES nunca. Sem eles o nuclei sai com
# "[FTL] Could not run nuclei: no templates provided for scan" e rc 1 -- o adapter e
# honesto (vira scanners_skipped), mas o nuclei NAO FUNCIONA em 100% dos scans
# "web" e "full", que sao justamente os que a UI promete com nuclei.
#
# Medido, e e por isso que existe o `-tl` abaixo: `nuclei -update-templates` falha
# com um WRN e devolve **rc 0** quando nao alcanca o GitHub. Um `RUN` ingenuo
# geraria imagem verde e vazia -- o mesmo silencio, agora no build. O gate conta os
# templates e reprova se vierem menos que o piso.
FROM debian:bookworm-slim AS nuclei-templates
ARG NUCLEI_VERSION=3.3.7
ARG NUCLEI_TEMPLATES_MIN=2000
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*
RUN set -eux; \
    curl -fsSL -o /tmp/nuclei.zip "https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VERSION}/nuclei_${NUCLEI_VERSION}_linux_amd64.zip" \
    && unzip -o /tmp/nuclei.zip nuclei -d /usr/local/bin && rm /tmp/nuclei.zip \
    && chmod +x /usr/local/bin/nuclei
# `-templates-directory` NAO EXISTE no nuclei v3 e o build morria aqui com
# "flag provided but not defined". O flag certo e `-ud/-update-template-dir`
# para baixar, e `-t <dir>` para listar. Medido em 2026-08-29, na primeira vez
# que a imagem foi buildada inteira -- ate entao os estagios tinham sido
# rodados um a um, e este erro so aparece no `docker build` completo.
RUN set -eux; \
    nuclei -update-templates -update-template-dir /opt/nuclei-templates; \
    total="$(nuclei -tl -t /opt/nuclei-templates -silent 2>/dev/null | wc -l)"; \
    echo "templates do nuclei: ${total}"; \
    if [ "${total}" -lt "${NUCLEI_TEMPLATES_MIN}" ]; then \
        echo "FALHA: so ${total} templates (piso ${NUCLEI_TEMPLATES_MIN}). O download" \
             "falhou em silencio -- o nuclei sairia sem verificar nada."; \
        exit 1; \
    fi; \
    echo "${total}" > /opt/nuclei-templates/TEMPLATE_COUNT

# ---- orchestrator -----------------------------------------------------------
FROM python:3.13-slim AS base

# nmap (port scan) — runs in-process. The heavier CLIs are copied from `tools`.
RUN apt-get update && apt-get install -y --no-install-recommends \
        nmap \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# Scanner CLIs bundled (nuclei / gitleaks / trufflehog / trivy).
# O trivy FALTAVA: o adapter chama o binário local (com --server apontando pro
# container), então sem ele o health() falhava e o scan era pulado EM SILÊNCIO — um
# scan de IMAGE não rodava nada e o relatório continuava listando "trivy".
COPY --from=tools /usr/local/bin/nuclei /usr/local/bin/gitleaks /usr/local/bin/trufflehog /usr/local/bin/trivy /usr/local/bin/

# Ruleset do Semgrep offline (~24MB). Sem ele o SAST -- o UNICO scanner que le o
# codigo -- depende do registry, e some justamente na rede restrita que e o
# ambiente-alvo deste projeto. O adapter escolhe por extensao do checkout quais
# diretorios carregar (repo Python nao paga o parsing das regras de Kotlin).
COPY --from=rules /opt/semgrep-rules /opt/semgrep-rules
ENV SEMGREP_RULES_DIR=/opt/semgrep-rules

# Templates do nuclei, offline. Sem eles o nuclei nao roda -- e ele e metade do que
# os profiles "web" e "full" prometem na tela do RoqueShield.
COPY --from=nuclei-templates /opt/nuclei-templates /opt/nuclei-templates
ENV NUCLEI_TEMPLATES_DIR=/opt/nuclei-templates

# uv para instalação rápida
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# instala dependências primeiro (camada cacheável) — inclui scanners Python
# (dnstwist, checkov) que rodam como subprocesso.
COPY pyproject.toml /app/
RUN uv pip install --system --no-cache-dir \
        fastapi "uvicorn[standard]" pydantic pydantic-settings \
        sqlmodel aiosqlite asyncpg "sqlalchemy[asyncio]" alembic \
        httpx structlog litellm \
        python-libnmap zaproxy \
        arq redis \
        PyGithub shodan \
        python-gvm \
        authlib "python-jose[cryptography]" "passlib[bcrypt]" itsdangerous \
        jinja2 pyyaml \
        dnstwist \
        semgrep \
        checkov \
        typer rich
# checkov (IaC) VOLTOU: a nota anterior dizia que a cadeia de dependência estava
# quebrada no Python 3.13, e isso venceu — checkov 3.3.15 instala e roda (verificado:
# 8 misconfigs num Terraform de teste). "Degrada graciosamente" era o problema, não a
# solução: o health() falhava, o scanner era pulado em silêncio, e o relatório
# continuava anunciando checkov num scan de REPO.

COPY orchestrator /app/orchestrator
COPY alembic.ini /app/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

ENTRYPOINT ["python", "-m", "orchestrator.cli"]
CMD ["--help"]
