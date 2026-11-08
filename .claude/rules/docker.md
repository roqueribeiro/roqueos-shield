---
description: Convenções de Docker compose, profiles, variáveis de ambiente
paths:
  - "docker/**"
  - "Dockerfile"
  - ".env.example"
  - "Makefile"
---

# Convenções de Docker

## Profiles

Compose modular com profiles:

| Profile | Inclui | Quando subir |
|---|---|---|
| `default` | orchestrator + worker + postgres + redis | sempre |
| `ollama` | ollama (reserva GPU NVIDIA) | só com GPU NVIDIA: `make ollama-up`. Fora do default porque numa máquina sem GPU o `up` inteiro falhava; no Mac, Ollama nativo no host |
| `scanners` | zap + trivy + kali-toolbox | quando rodar scans |
| `lab` | juice-shop + dvwa + webgoat | testes/desenvolvimento |
| `greenbone` | stack Greenbone (~20 containers) | scan rede sob demanda |
| `obs` | phoenix tracing | debug AI |
| `ai-agent` | cai-expert | Fase 4 agentic |
| `proxy` | caddy TLS | Fase 6 hardening |

Com `docker compose -f docker/...`, sempre passar `--env-file .env --project-directory docker`: sem o primeiro, o `.env` da raiz não é lido; sem o segundo, os caminhos `../` dos compose não resolvem a partir de `docker/`. O Makefile já passa os dois (`COMPOSE_FLAGS`); prefira o target do Makefile ao comando solto.

A CLI do motor via compose troca o entrypoint, porque o orchestrator tem `entrypoint: uvicorn`:
`docker compose ... run --rm --entrypoint python orchestrator -m orchestrator.cli scan ...`. Sem o `--entrypoint`, `run orchestrator scan ...` vira `uvicorn scan ...`. É o `CLI` do Makefile, usado por `make scan`, `make scan-no-ai` e `make exposure`.

## Network

- `cai-net` (bridge) é a rede compartilhada — todo container roda nela
- Portas SEMPRE em `127.0.0.1:<host_port>:<container_port>`. **Nunca expor em `0.0.0.0`** sem motivo justificado (compliance bancário)
- `extra_hosts: ["host.docker.internal:host-gateway"]` no orchestrator pra falar com LM Studio no host Windows

## Volumes

Nomeados, persistentes:
- `pgdata` — Postgres
- `ollama_models` — modelos LLM baixados
- `trivy_cache` — DB de vulns Trivy
- `kali_workspace` — workspace efêmero pro Kali toolbox
- `gvm_*` — Greenbone (vários)
- `caddy_data` / `caddy_config` — TLS interno

`./reports`, `./data`, `./config` são bind-mounts.

## Permissões de container

- `orchestrator` e `worker`: `cap_drop: [ALL]`, `no-new-privileges:true`, não-root (UID 1000) e `read_only: true`. Nenhum dos dois tem `cap_add`.
- O nmap roda no worker sem root e sem `NET_RAW`, então faz connect scan (`-sT -Pn`), não SYN scan. Decisão da Issue #12 (08/11/2026): não haverá worker separado com `NET_RAW` só para o nmap. Se um dia o adapter precisar de raw socket, a capability vai num serviço próprio, nunca no worker que roda os outros scanners.
- Raiz só de leitura: o que orchestrator e worker escrevem vai para `/app/reports` e `/app/data` (bind mounts), `/tmp` (tmpfs: mkdtemp dos adapters e clone do repo escaneado; 2 GiB no worker) e o HOME `/home/roqueos` (tmpfs: config e cache de semgrep, nuclei e trivy). Scanner que precisa escrever em outro lugar pede um tmpfs novo no `docker/compose.yml`.
- `kali-toolbox`: `cap_drop: [ALL]` e `no-new-privileges:true`.
- O único `cap_add` da stack é o `greenbone-ospd` (`NET_ADMIN`, `NET_RAW`) em `compose.greenbone.yml`, que é upstream do Greenbone.
- **Nunca usar `--privileged`** sem aprovação
- Containers que NÃO precisam de rede pra fora: não dar `network_mode: host`

## .env

- `.env.example` é template versionado
- `.env` é gitignored — NUNCA commitar
- `pydantic-settings` em `orchestrator/config.py` define o schema
- Adicionar variável nova: atualizar `config.py` + `.env.example` + doc no README

## Imagens

| Imagem | Origem | Tamanho aprox |
|---|---|---|
| `cai-orchestrator:dev` | `docker/images/orchestrator/Dockerfile` | ~500MB |
| `cai-kali-toolbox:dev` | `docker/images/kali-toolbox/Dockerfile` | ~3GB (downloads) |
| `cai-expert:dev` | `docker/images/cai-expert/Dockerfile` | ~1GB |
| `zaproxy/zap-stable` | upstream | ~700MB |
| `aquasec/trivy` | upstream | ~150MB |
| `bkimminich/juice-shop` | upstream | ~250MB |

Build de tudo pode demorar 15-30min na primeira vez. `make build` builda `orchestrator`/`worker` (mesma imagem), depois `kali-toolbox`, e tenta o `cai-expert` (falha nele só avisa).

## Healthcheck

O que existe hoje no compose de dev:

| Serviço | Checagem | Observação |
|---|---|---|
| `orchestrator` | `python -c urllib.request.urlopen('http://localhost:8080/health')` | `start_period: 30s`; a imagem não depende de curl para isso |
| `zap` | `curl -fsS -o /dev/null http://127.0.0.1:8090/` | `start_period: 120s`; sem a chave da API na URL, de propósito |
| `postgres` | `pg_isready -U cai -d cai` | |
| `redis` | `redis-cli ping` | |
| `worker` | nenhum | o arq não expõe porta; fila parada aparece no `/health/full` (redis) e no job preso em QUEUED |

Para esperar um serviço, leia o estado do healthcheck (`docker inspect -f '{{.State.Health.Status}}' cai-zap`) em vez de chamar a API com a chave na URL: segredo não vai para argv.

## Portas que confundem

- GSA (Greenbone web): `http://127.0.0.1:9392`, em **http**. O container serve na porta 80 (`127.0.0.1:9392:80`); não há TLS nele.
- GMP (Greenbone, TCP): `127.0.0.1:9390`.

## Não fazer

- Não rodar `docker compose down -v` em produção (apaga volumes = apaga DB)
- Não modificar `compose.greenbone.yml` ad-hoc — reflita mudanças no upstream Greenbone
- Não adicionar `:latest` em imagens críticas em produção — pin de versão
