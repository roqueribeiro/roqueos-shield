# CAI orchestrator — comprehensive image.
#
# Bundles the heavy scanner CLIs (nuclei / gitleaks / trufflehog) + Python
# scanners (dnstwist / checkov) directly in the orchestrator+worker image so the
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
ARG TRIVY_VERSION=0.58.1
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
