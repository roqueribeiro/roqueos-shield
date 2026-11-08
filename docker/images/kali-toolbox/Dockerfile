FROM kalilinux/kali-rolling:latest

# Update + ferramentas Kali essenciais para nossos adapters.
# Mantemos enxuto: NÃO usamos kali-linux-large (vai a >12GB).
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl wget jq git \
        nmap masscan \
        ffuf gobuster dirsearch \
        sqlmap nikto \
        amass \
        whois dnsutils \
        openssh-client \
        python3 python3-pip python3-venv \
        ruby \
    && rm -rf /var/lib/apt/lists/*

# Binários pré-compilados, com versão pinada e arquitetura do build (amd64 ou arm64).
# Antes eram URLs `latest/download/<versão velha>` e amd64 fixo, com `|| true` e
# `|| echo fallback`: a imagem saía verde e sem nuclei, e o passo dos templates
# abaixo quebrava o `make build` com "nuclei: not found". Agora download que falha
# derruba o build (curl -f e set -e), e cada binário prova que executa.
ARG TARGETARCH=amd64
ARG SUBFINDER_VERSION=2.17.0
ARG HTTPX_VERSION=1.12.0
ARG NUCLEI_VERSION=3.11.1
ARG NAABU_VERSION=2.7.0
ARG GITLEAKS_VERSION=8.30.1
ARG TRUFFLEHOG_VERSION=3.99.2
ARG TRIVY_VERSION=0.76.0
ARG KUBEBENCH_VERSION=0.16.0
RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends unzip libpcap0.8 \
        && rm -rf /var/lib/apt/lists/*; \
    ARCH="${TARGETARCH}"; \
    case "$ARCH" in \
      amd64) GL_ARCH=x64;   TV_ARCH=Linux-64bit ;; \
      arm64) GL_ARCH=arm64; TV_ARCH=Linux-ARM64 ;; \
      *) echo "arquitetura sem binario publicado: $ARCH" >&2; exit 1 ;; \
    esac; \
    cd /tmp; \
    for pd in "subfinder:${SUBFINDER_VERSION}" "httpx:${HTTPX_VERSION}" "nuclei:${NUCLEI_VERSION}" "naabu:${NAABU_VERSION}"; do \
      n="${pd%%:*}"; v="${pd##*:}"; \
      curl -fsSL -o "$n.zip" "https://github.com/projectdiscovery/$n/releases/download/v$v/${n}_${v}_linux_${ARCH}.zip"; \
      unzip -o "$n.zip" "$n" -d /usr/local/bin; rm "$n.zip"; \
    done; \
    curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${GL_ARCH}.tar.gz" | tar -xz -C /usr/local/bin gitleaks; \
    curl -fsSL "https://github.com/trufflesecurity/trufflehog/releases/download/v${TRUFFLEHOG_VERSION}/trufflehog_${TRUFFLEHOG_VERSION}_linux_${ARCH}.tar.gz" | tar -xz -C /usr/local/bin trufflehog; \
    curl -fsSL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_${TV_ARCH}.tar.gz" | tar -xz -C /usr/local/bin trivy; \
    curl -fsSL "https://github.com/aquasecurity/kube-bench/releases/download/v${KUBEBENCH_VERSION}/kube-bench_${KUBEBENCH_VERSION}_linux_${ARCH}.tar.gz" | tar -xz -C /usr/local/bin kube-bench; \
    chmod +x /usr/local/bin/subfinder /usr/local/bin/httpx /usr/local/bin/nuclei /usr/local/bin/naabu \
             /usr/local/bin/gitleaks /usr/local/bin/trufflehog /usr/local/bin/trivy /usr/local/bin/kube-bench; \
    for b in subfinder httpx nuclei naabu gitleaks trufflehog trivy kube-bench; do \
      "$b" -version >/dev/null 2>&1 || "$b" --version >/dev/null 2>&1 || "$b" version >/dev/null 2>&1 \
        || { echo "$b nao executa em $ARCH" >&2; exit 1; }; \
    done

# Cloud / IaC
# --ignore-installed: o kali-rolling traz `packaging` instalado pelo apt, sem RECORD,
# e o pip não consegue desinstalar para atualizar (uninstall-no-record-file).
RUN pip install --break-system-packages --ignore-installed --no-cache-dir \
        checkov \
        dnstwist

# Templates do nuclei. O `|| true` que estava aqui gerava imagem verde e VAZIA:
# medido, o `-update-templates` falha com um WRN e devolve rc 0 quando nao alcanca
# o GitHub, e o nuclei so descobre no scan, com "no templates provided".
ARG NUCLEI_TEMPLATES_MIN=2000
# Em /opt e legível por todos: o agente roda como UID 1000, que não lê o /root.
RUN set -eux; \
    nuclei -update-templates -update-template-dir /opt/nuclei-templates; \
    total="$(nuclei -tl -t /opt/nuclei-templates -silent 2>/dev/null | wc -l)"; \
    echo "templates do nuclei: ${total}"; \
    [ "${total}" -ge "${NUCLEI_TEMPLATES_MIN}" ] || { echo "FALHA: so ${total} templates"; exit 1; }; \
    chmod -R a+rX /opt/nuclei-templates

# gvm-tools (cliente Greenbone GMP)
RUN pip install --break-system-packages --ignore-installed --no-cache-dir gvm-tools python-gvm

WORKDIR /workspace

# O agente ofensivo executa comando aqui: nunca como root (Issue #12). Ferramenta que
# exige raw socket (masscan, nmap -sS) falha alto em vez de rodar privilegiada.
RUN useradd --uid 1000 --create-home --shell /bin/bash agente && chown 1000:1000 /workspace

# Pequena verificação de bins instalados (diagnóstico)
RUN echo "Installed:" \
    && (nmap --version | head -1) \
    && (nuclei -version 2>&1 | head -1) \
    && (gitleaks version 2>&1 | head -1) \
    && (trufflehog --version 2>&1 | head -1) \
    && (dnstwist --help >/dev/null && echo dnstwist ok) \
    && (trivy --version 2>&1 | head -1)

USER 1000
