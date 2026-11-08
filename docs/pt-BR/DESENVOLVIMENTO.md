# Desenvolvimento

*Tradução de [DEVELOPMENT.md](../DEVELOPMENT.md), a versão principal, em inglês. Se as duas divergirem, vale a em inglês.*

> Para quem muda o código do RoqueShield. Esta é a stack de desenvolvimento: Docker Compose, Postgres e um container por peça. Para **usar** o RoqueShield, instale o container standalone: [COMECAR.md](COMECAR.md), e [OPERACAO.md](OPERACAO.md) para o dia a dia dele. Como testar está em [CRITERIOS-DE-TESTE.md](CRITERIOS-DE-TESTE.md); como adicionar um scanner, em [ESTENDER.md](ESTENDER.md); as regras de pull request, em [CONTRIBUTING.md](CONTRIBUTING.md).

## Sumário

1. [Stack de desenvolvimento ou standalone](#1-stack-de-desenvolvimento-ou-standalone)
2. [O que você precisa](#2-o-que-você-precisa)
3. [Primeira subida](#3-primeira-subida)
4. [Os containers](#4-os-containers)
5. [Dia a dia](#5-dia-a-dia)
6. [A tela web](#6-a-tela-web)
7. [Gates locais](#7-gates-locais)
8. [O CI](#8-o-ci)
9. [Backup e atualização da stack de desenvolvimento](#9-backup-e-atualização-da-stack-de-desenvolvimento)
10. [Claude Code: skills, comandos e agentes](#10-claude-code-skills-comandos-e-agentes)
11. [Quando algo não funciona](#11-quando-algo-não-funciona)

Sobre nomes: `cai` é o nome interno do motor. É o pacote Python (`cai-orchestrator`), a CLI de administração (`cai`), o projeto do Compose (`name: cai`) e o prefixo de todo container de desenvolvimento (`cai-*`). O produto é o RoqueShield, e a CLI cliente é `roqueshield`.

## 1. Stack de desenvolvimento ou standalone

Há dois jeitos de subir o RoqueShield, e eles não são a mesma coisa.

| | Stack de desenvolvimento | Standalone |
| --- | --- | --- |
| Para quem | quem muda o código | quem usa a ferramenta |
| Como sobe | `make up` (arquivos do Compose em `docker/`) | `install.sh`, um `docker run` |
| Containers | um por peça: API, worker, Postgres, Redis, ZAP, Trivy, alvos de laboratório | um: motor, ZAP, Redis e a tela web juntos |
| Imagem | `cai-orchestrator:dev`, buildada na sua máquina | `roqueribeiro1988/roqueos-shield:vX.Y.Z-standalone`, do Docker Hub |
| Banco | Postgres (`cai-postgres`), schema pelo `make migrate` | SQLite no volume `/data`, tabelas criadas no boot |
| Tela em `/` | nenhuma: `/` redireciona para o dashboard antigo em `/ui/` | a tela web de `web/` |

A imagem de desenvolvimento não leva a tela web: o `.dockerignore` deixa `orchestrator/web_dist` fora do contexto do build, de propósito, para um build local esquecido não vazar para a imagem do motor. Para trabalhar na tela, veja a [seção 6](#6-a-tela-web).

Para buildar a imagem standalone você mesmo e instalar como um usuário instalaria, veja [CONTRIBUTING.md](CONTRIBUTING.md#a-imagem-standalone). Atualização, backup e todo o resto do container standalone estão em [OPERACAO.md](OPERACAO.md).

Existe também o `docker/compose.prod.yml` (projeto `roqueshield`): a imagem standalone dividida em serviços com Postgres, para produção. Esse é de operação, não de desenvolvimento.

## 2. O que você precisa

- **Docker Engine** (Linux) ou **Docker Desktop** (WSL2 no Windows) com Compose v2.
- **make** e **bash**.
- **Python 3.13** para os testes e gates que rodam fora do Docker (`requires-python = ">=3.13"` no `pyproject.toml`).
- **Node 22** e **yarn** se você mexer em `web/`. O CI usa Node 22.20.0. Nunca npm: o lockfile é `web/yarn.lock`.
- **8 GB de RAM livre** para a stack completa. Só o container do ZAP tem teto de 6 GB (`mem_limit: 6g` em `docker/compose.scanners.yml`).
- Uma **GPU NVIDIA** só se você quiser o container `cai-ollama` (perfil `ollama`, fora do default). No Mac, ou numa máquina sem GPU, rode o Ollama nativo e aponte `LLM_LOCAL_BASE_URL` para `http://host.docker.internal:11434/v1`.
- O **uv** para `make test` e `make lint`, que rodam no seu checkout, não na imagem.
- Uma **chave da Anthropic ou da OpenAI** é opcional. Sem ela, faça scan com `make scan-no-ai`.

## 3. Primeira subida

```bash
git clone https://github.com/roqueribeiro/roqueos-shield.git
cd roqueos-shield
cp .env.example .env

# Segredos fortes, sem imprimir nenhum. Hex, porque base64 pode ter "/",
# que quebra a expressão do sed.
for k in APP_TOKEN ZAP_API_KEY POSTGRES_PASSWORD; do
  sed -i.bak "s|^$k=.*|$k=$(openssl rand -hex 24)|" .env
done
# O DATABASE_URL também leva a senha do Postgres: mantenha os dois iguais.
pg="$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)"
sed -i.bak "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://cai:${pg}@postgres:5432/cai|" .env
rm .env.bak

make build      # cai-orchestrator:dev, cai-kali-toolbox:dev e, se buildar, cai-expert:dev
make up         # perfis default + scanners + lab
make migrate    # alembic upgrade head no cai-postgres
```

Três coisas que os comandos acima resolvem, e por quê:

- **A API se recusa a subir com o token de exemplo.** `APP_TOKEN` vazio, `dev-changeme`, `dev-changeme-with-strong-random`, `changeme` ou `change-me` para o boot (`orchestrator/config.py`), a não ser com `ALLOW_INSECURE_APP_TOKEN=true`.
- **O `DATABASE_URL` do `.env.example` tem a senha de exemplo escrita nele.** Trocar só o `POSTGRES_PASSWORD` deixa um Postgres com uma senha e uma API tentando outra.
- **O Postgres lê a senha uma vez só**, quando o volume `pgdata` é criado. Mudar depois no `.env` não faz nada num volume que já existe.

**O que você deve ver** depois do `make up`, impresso pelo Makefile:

```
Stack no ar:
  orchestrator API : http://127.0.0.1:8080  (X-API-Token: $APP_TOKEN)
  zap              : http://127.0.0.1:8090
  trivy            : http://127.0.0.1:4954
  juice-shop       : http://127.0.0.1:3000
  dvwa             : http://127.0.0.1:8000
  webgoat          : http://127.0.0.1:8081
Ollama local é à parte: make ollama-up (GPU NVIDIA) ou o Ollama nativo do host.
```

Depois confira:

```bash
curl http://127.0.0.1:8080/health
# {"status":"ok","version":"..."}

# o token vai num arquivo de cabeçalho 0600, não no argv do curl (que aparece no ps)
H="$(mktemp)"; chmod 600 "$H"
printf 'X-API-Token: %s\n' "$(grep '^APP_TOKEN=' .env | cut -d= -f2)" > "$H"
curl -s http://127.0.0.1:8080/health/full -H @"$H"
```

`/health` é liveness, sem autenticação. `/health/full` pede o token e confere Postgres, Redis, ZAP, o LLM e se cada binário de scanner existe na imagem. Scanner listado em `ausentes` não roda, e o vetor dele fica sem verificação.

## 4. Os containers

Todos escutam só em 127.0.0.1. Postgres e Redis não publicam porta: só são alcançados de dentro da rede `cai-net`.

| Container | Arquivo do Compose | Perfil | Porta na sua máquina | O que é |
| --- | --- | --- | --- | --- |
| `cai-orchestrator` | `compose.yml` | default, scanners | 8080 | a API (uvicorn) |
| `cai-worker` | `compose.yml` | default, scanners | nenhuma | o worker arq que roda os scans |
| `cai-postgres` | `compose.yml` | default, scanners | nenhuma | Postgres 16 |
| `cai-redis` | `compose.yml` | default, scanners | nenhuma | a fila de jobs |
| `cai-ollama` | `compose.yml` | ollama | 11434 | modelos locais (reserva GPU NVIDIA) |
| `cai-zap` | `compose.scanners.yml` | scanners | 8090 | daemon do OWASP ZAP |
| `cai-trivy` | `compose.scanners.yml` | scanners | 4954 | Trivy em modo servidor (cache de base compartilhado) |
| `cai-kali-toolbox` | `compose.scanners.yml` | scanners | nenhuma | imagem Kali mantida de pé para `docker exec` |
| `cai-juice-shop` | `compose.lab.yml` | lab | 3000 | alvo vulnerável |
| `cai-dvwa` | `compose.lab.yml` | lab | 8000 | alvo vulnerável |
| `cai-webgoat` | `compose.lab.yml` | lab | 8081, 9090 | alvo vulnerável |
| `cai-gvm-feeds`, `cai-gvm-redis`, `cai-gvm-postgres`, `cai-gvmd`, `cai-ospd-openvas` | `compose.greenbone.yml` | greenbone | nenhuma | Greenbone Community, mínimo |
| `cai-gvm-gmp-tcp` | `compose.greenbone.yml` | greenbone | 9390 | GMP por TCP, para o orchestrator |
| `cai-gsa` | `compose.greenbone.yml` | greenbone | 9392 | tela web do Greenbone, em HTTP simples (`http://127.0.0.1:9392`; o container serve a porta 80) |
| `cai-phoenix` | `compose.observability.yml` | obs | 6006, 4317 | tracing Phoenix (tela e OTLP gRPC) |
| `cai-expert` | `compose.agent.yml` | ai-agent | nenhuma | container do agente, `sleep infinity` |
| `cai-caddy` | `compose.proxy.yml` | proxy | 443 | proxy reverso TLS para `cai.local` |

Os scanners rodam dentro do `cai-worker`, como subprocessos. A imagem do orchestrator leva nmap, nuclei, gitleaks, trufflehog, trivy, semgrep (com o ruleset offline em `/opt/semgrep-rules`), dnstwist e checkov (num venv próprio). O `cai-kali-toolbox` não é onde o scan roda.

**O Ollama tem perfil próprio, `ollama`**, e reserva uma GPU NVIDIA (`deploy.resources.reservations.devices`). Até 08/11/2026 ele estava no `default`, e numa máquina sem o runtime NVIDIA para containers o `make up` e o `make api` paravam nele. Agora nenhum dos dois sobe o Ollama; quem sobe é o `make ollama-up`. Sem GPU, rode o Ollama nativo no host e defina `LLM_LOCAL_BASE_URL=http://host.docker.internal:11434/v1`.

**Endurecimento do `cai-orchestrator` e do `cai-worker`** (Issue #12): não-root (UID 1000), `cap_drop: ALL`, `no-new-privileges` e **raiz só de leitura** (`read_only: true`). O que eles escrevem tem lugar próprio: `reports/` e `data/` (bind mounts), `/tmp` em tmpfs (256 MiB na API, 2 GiB no worker, onde o repo escaneado é clonado) e a pasta home `/home/roqueos` em tmpfs (semgrep e nuclei guardam config e cache ali). Scanner que falha com `Read-only file system` está escrevendo em outro lugar: dê um tmpfs para esse caminho, não tire o `read_only`. O nmap faz connect scan (`-sT -Pn`), então nenhum container precisa de `NET_RAW`; um worker separado para o nmap, numa rede própria, foi considerado na #12 e descartado por isso.

**A chave da API do ZAP não vai na linha de comando.** O `cai-zap` recebe `ZAP_API_KEY` pelo ambiente; o entrypoint grava um arquivo de propriedades `0600`, apaga a variável e sobe o ZAP com `-configfile`. A chave não aparece no `ps` nem no `docker inspect` (`Config.Cmd`). O `cai-zap` e o `cai-orchestrator` têm healthcheck; o `docker ps` mostra `healthy` quando o ZAP abre a porta (um a dois minutos).

A configuração do Greenbone (feed sync, credenciais) e do LM Studio está em [OPERACAO.md](OPERACAO.md).

## 5. Dia a dia

O Makefile esconde as flags do Compose. `make help` lista todos os alvos; são estes:

| Alvo | O que faz |
| --- | --- |
| `make build` | builda `orchestrator`/`worker`, depois `kali-toolbox`, depois `cai-expert` (falha no último imprime um aviso e não para o alvo) |
| `make up` | perfis default, scanners e lab |
| `make api` | perfil default: orchestrator, worker, Postgres e Redis, sem scanners externos nem lab |
| `make ollama-up` | o container `cai-ollama` (perfil `ollama`, pede GPU NVIDIA) |
| `make down` | desce todo serviço de todo arquivo de compose e perfil, mantendo os volumes |
| `make ps` / `make logs` | estado dos containers / acompanha os logs do orchestrator e do worker |
| `make shell` | bash num container descartável do orchestrator |
| `make scan TARGET=<url>` | scan síncrono pela CLI `cai scan`, com triagem de IA; `AUTH_REF=` quando `REQUIRE_AUTH_REF=true`; flags extras em `EXTRA=` |
| `make scan-no-ai TARGET=<url>` | o mesmo, com `--skip-ai` |
| `make scan-api TARGET_ID=<uuid>` | `POST /scans`; os scanners saem do `asset_type` do alvo (`AUTH_REF=` acrescenta `authorization_ref`) |
| `make exposure` | scan OSINT (`cai exposure`), configurado por `config/exposure_targets.yml` |
| `make smoke` | `scripts/smoke.sh`: build, up e um scan ativo no Juice Shop |
| `make migrate` / `make revision NAME=...` | `alembic upgrade head` / migration nova autogerada |
| `make test` / `make lint` | pytest / `ruff check` e `ruff format --check`, no seu checkout por `uv run --frozen --extra dev` (`ARGS=tests/unit/test_x.py` para um alvo) |
| `make typecheck` | mypy em modo strict, gate bloqueante no CI |
| `make ollama-pull` | baixa os modelos padrão do Ollama |
| `make greenbone-up` / `make greenbone-down` | a stack do Greenbone (feed sync de 30 min a 3 h, uns 5 GB) |
| `make obs-up` / `make agent-up` / `make proxy-up` | Phoenix / `cai-expert` / Caddy |
| `make backup` | dump do Postgres (a trilha de auditoria é tabela dele) e `reports/`; veja a [seção 9](#9-backup-e-atualização-da-stack-de-desenvolvimento) |
| `make clean` | desce tudo e **apaga** os volumes e tudo em `reports/` e `data/` |

O `TARGET` padrão é `http://juice-shop:3000`: o nome dentro da `cai-net`, não `localhost`.

Os alvos de CLI (`scan`, `scan-no-ai`, `exposure`) trocam o entrypoint por `python -m orchestrator.cli`: o entrypoint do orchestrator no compose é `uvicorn`, e antes de 08/11/2026 o `make scan` virava `uvicorn scan ...`.

`make test` e `make lint` rodam no seu checkout, não na imagem. A imagem é buildada com `uv export --no-dev` e não tem `tests/`, pytest, ruff nem mypy. Até 08/11/2026 os dois alvos rodavam dentro dela e não tinham como funcionar.

Um scan pela API, de ponta a ponta:

```bash
# o token vai num arquivo de cabeçalho 0600, não no argv do curl (que aparece no ps)
H="$(mktemp)"; chmod 600 "$H"
printf 'X-API-Token: %s\n' "$(grep '^APP_TOKEN=' .env | cut -d= -f2)" > "$H"

TARGET_ID=$(curl -s -X POST http://127.0.0.1:8080/targets \
  -H "Content-Type: application/json" -H @"$H" \
  -d '{"asset_type":"url","value":"http://juice-shop:3000","criticality":"medium"}' | jq -r .id)

SCAN_ID=$(curl -s -X POST http://127.0.0.1:8080/scans \
  -H "Content-Type: application/json" -H @"$H" \
  -d "{\"target_id\":\"$TARGET_ID\",\"scanners\":[\"nmap\",\"zap\"]}" | jq -r .id)

curl -s http://127.0.0.1:8080/scans/$SCAN_ID -H @"$H" | jq .state
curl -s http://127.0.0.1:8080/reports/$SCAN_ID -H @"$H" -o report.html
```

A CLI de administração dentro da imagem é a `cai` (`python -m orchestrator.cli` é o entrypoint da imagem, então `run --rm orchestrator <subcomando>` chama ela). Os comandos são `scan`, `exposure`, `serve` e `bundle`; `cai scan --help` lista `--asset-type`, `--criticality`, `--contains-pii`, `--skip-ai`, `--active-zap` e `--ajax`.

## 6. A tela web

A tela que o standalone serve é um app Vue 3 + Quasar em `web/`. Ela não está na imagem de desenvolvimento. Dois jeitos de trabalhar nela:

```bash
cd web
yarn install
yarn dev        # Quasar em http://127.0.0.1:9100, chamadas da API repassadas para 127.0.0.1:8080
```

O `yarn dev` repassa `/setup`, `/auth`, `/settings`, `/system`, `/scans`, `/targets`, `/findings`, `/reports`, `/ui/api`, `/users`, `/health`, `/investigate` e `/exposure` para a porta 8080 (`web/quasar.config.js`), então funciona contra `make api` ou `make up`.

Para testar a tela como o CI testa:

```bash
cd web && yarn install --frozen-lockfile && yarn build && cd ..
scripts/web_e2e.sh
```

O `yarn build` escreve `orchestrator/web_dist`. O `scripts/web_e2e.sh` sobe um shield descartável (uvicorn, SQLite novo, sem Redis) na porta 8099 (`E2E_PORTA` muda) e roda `web/e2e/standalone.e2e.mjs` contra ele. Os segredos e a senha do admin de teste são gerados numa pasta temporária 0600 e nunca vão para a tela. Sem `orchestrator/web_dist` ele para com `falta orchestrator/web_dist: rode (cd web && yarn build) antes` e sai com 2. Na primeira vez, o Playwright precisa do Chromium dele: `cd web && yarn playwright install chromium`.

Os textos ficam em `web/src/i18n/`. As capturas de tela da documentação saem do `scripts/doc_capturas.sh`, nunca de print à mão.

## 7. Gates locais

Não há ferramenta de gate do repositório aqui. O `roqueos-gate` é do harness do RoqueOS, não deste repositório. O que este repositório tem são os scripts abaixo, os mesmos que o CI roda. Nenhum precisa de Docker.

Primeiro, um ambiente com as dependências de desenvolvimento, como o CI monta:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

| Comando | O que segura | Job do CI |
| --- | --- | --- |
| `.venv/bin/ruff check orchestrator tests scripts` | lint | `lint` |
| `.venv/bin/ruff format --check orchestrator tests scripts` | formatação | `lint` |
| `.venv/bin/mypy orchestrator` | tipos, strict (bloqueia o merge) | `typecheck` |
| `.venv/bin/pytest --cov=orchestrator --cov-fail-under=64` | a suíte e o piso de cobertura | `test` |
| `python scripts/check_no_silence.py` | o contrato do silêncio, por AST | `silencio` |
| `python scripts/check_docs_fresh.py` | a doc contra o código: scanners, contagem de adapters, `.env.example`, afirmações vencidas, versão do instalador, pares de docs e links | `docs` |
| `python scripts/gen_diagrams.py --check` | os SVGs em `docs/assets/` são o que o gerador produz agora | `diagramas` |
| `.venv/bin/python scripts/openapi_snapshot.py --check` | o `docs/openapi.json` bate com a API (também é teste: `test_openapi_snapshot.py`) | `test` |
| `uv lock --check` | o `uv.lock` bate com o `pyproject.toml` | `lockfile` |
| `scripts/web_e2e.sh` | a tela web contra um shield de verdade | `web` |

O CI pina `ruff==0.16.5` (o extra `dev` pina o mesmo). Outra versão do ruff pode discordar da formatação.

**O que você deve ver** dos três gates em Python numa árvore limpa:

```
contrato do silêncio: 27 arquivos (adapters + pipeline + exporters), nenhum zero silencioso; a persistência grava a cobertura.
doc em dia: scanners, variáveis e afirmações batem com o código.
OK: <n> diagramas em dia.
```

Cada um sai com 1 e lista as divergências quando reprova.

O `scripts/release-docker.sh` não é gate para rodar antes de um pull request. É o caminho de release dos mantenedores: builda e publica `vX.Y.Z` e `vX.Y.Z-standalone` no Docker Hub, e recusa tag ausente ou fora do HEAD, árvore suja, versão que já está no Hub, manifesto sem amd64 e arm64, e Trivy com CRITICAL ou HIGH que tenha correção.

## 8. O CI

`.github/workflows/ci.yml`, em push para `main` e em pull request para `main`:

| Job | O que roda | Quando |
| --- | --- | --- |
| `lint` | ruff check e ruff format --check | sempre |
| `lockfile` | `uv lock --check` | sempre |
| `docs` | `scripts/check_docs_fresh.py` | sempre |
| `diagramas` | `scripts/gen_diagrams.py --check` | sempre |
| `silencio` | `scripts/check_no_silence.py` | sempre |
| `secrets` | gitleaks no histórico inteiro, com `.gitleaks.toml` | sempre |
| `self-scan` | Semgrep (`p/security-audit`, `p/secrets`) sobre `orchestrator/` e `scripts/` | sempre |
| `efetividade` | `tests/integration/test_efetividade_e2e.py` com semgrep e checkov instalados | sempre |
| `typecheck` | `mypy orchestrator` em modo strict, mypy pinado no extra dev | sempre |
| `test` | pytest com `--cov-fail-under=64` | sempre |
| `web` | idade do lock, `yarn install --frozen-lockfile`, `yarn build`, Playwright, `scripts/web_e2e.sh` | sempre |
| `build-image` | builda a imagem do orchestrator, sem push | pull request |
| `standalone-image` | builda motor e standalone, espera `healthy`, confere `/setup`, a CLI e os templates do nuclei | pull request |
| `publish-image` | publica `ghcr.io/<owner>/cai-orchestrator` | push na `main`, depois de lint, web, typecheck, test, silencio, efetividade |

O job web também roda `web/scripts/idade-do-lock.mjs`, que reprova quando alguma versão do `yarn.lock` tem menos de 14 dias.

## 9. Backup e atualização da stack de desenvolvimento

```bash
make backup
```

O `scripts/backup.sh` escreve `backups/<AAAAMMDD-HHMMSS>/cai.sql.gz` (um `pg_dump` do `cai-postgres`) e `reports.tar.gz` (a pasta `reports/`). A trilha de auditoria fica dentro do Postgres, então vai junto com o dump. Não há alvo de restauração. O dump é SQL puro: restaurar é entregar ele ao `psql` num banco vazio. Esse caminho não foi exercitado para este documento.

Atualização:

```bash
git pull
make build
make migrate
make up
```

`make migrate` antes do `make up`: o código novo espera o schema novo. Erro do Postgres `relation does not exist` é migration que não rodou.

Backup e atualização do container **standalone** são outro procedimento, pelo `install.sh --update`: [OPERACAO.md](OPERACAO.md).

## 10. Claude Code: skills, comandos e agentes

A pasta `.claude/` guarda o que o Claude Code carrega neste repositório.

**Comandos** (`.claude/commands/`, chamados como `/nome`):

| Comando | O que roda |
| --- | --- |
| `/up`, `/down`, `/build`, `/migrate`, `/logs`, `/status` | a stack: compose up e down, build, alembic, logs, diagnóstico rápido |
| `/dashboard` | sobe a stack se precisar e imprime a URL de `/ui/` com o token |
| `/test`, `/lint` | pytest, e ruff com mypy, no seu checkout por `uv run` (como `make test` e `make lint`, [seção 5](#5-dia-a-dia)) |
| `/smoke` | `scripts/smoke.sh` |
| `/bundle <scan_id>` | `cai bundle`: o AI Fix Bundle de um scan |
| `/backup` | `scripts/backup.sh` |
| `/db-shell` | `psql` no `cai-postgres`, leitura e escrita |

Toda chamada de `docker compose` neles passa `--env-file .env --project-directory docker`, como o Makefile. O `scripts/smoke.sh` explica por quê: no Compose v5 os caminhos relativos resolvem contra o diretório do projeto, e sem a flag o contexto do build quebra; e com `-f docker/...` o Compose procuraria o `.env` dentro de `docker/`.

**Skills** (`.claude/skills/`): `cai-scan`, `cai-triage`, `cai-investigate`, `cai-exposure`, `cai-handoff-fix`, `cai-stack-status`, `cai-self-heal`, `cai-llm-debug`, `cai-add-adapter` e `cai-deploy` (que só roda quando pedido explicitamente). Cada uma é acionada pela descrição dela: "isso quebrou" chama a `cai-self-heal`, "testa o LLM" chama a `cai-llm-debug`.

**Agentes** (`.claude/agents/`): `adapter-author` (escreve adapter novo; o template dele, o da skill `cai-add-adapter` e o de `.claude/rules/scanners.md` seguem o contrato do silêncio), `findings-analyst` (explora achados no banco), `fix-bundle-author` (enriquece AI Fix Bundles) e `security-auditor` (revisa um diff como atacante e como defensor).

**Regras** (`.claude/rules/`): `scanners.md`, `testing.md`, `api.md`, `docker.md`, `triage.md`, `50-docs-vivas.md` e `60-contrato-do-silencio.md`. As duas últimas são as que têm gate por trás: `check_docs_fresh.py` e `check_no_silence.py`.

**Hook**: `.claude/hooks/format-python.py`, depois de todo Edit ou Write, formata o `.py` editado com o ruff quando o ruff está instalado.

`python .claude/_validate.py` valida frontmatters, JSON e referências internas da `.claude/`.

## 11. Quando algo não funciona

- **`make ollama-up` para em `could not select device driver "nvidia"`**: não há runtime NVIDIA nesta máquina. Rode o Ollama nativo no host, como na [seção 4](#4-os-containers).
- **Um scanner falha com `Read-only file system`**: a raiz do `cai-worker` é só de leitura. Veja em que caminho ele escreve e dê um tmpfs para ele no `docker/compose.yml` ([seção 4](#4-os-containers)).
- **A API reinicia em loop e o log fala de `APP_TOKEN`**: o token ainda é o de exemplo. Gere como na [seção 3](#3-primeira-subida).
- **A API não autentica no Postgres**: `DATABASE_URL` e `POSTGRES_PASSWORD` discordam, ou o volume `pgdata` foi criado com outra senha. Alinhe os dois; para um volume novo, `make clean` apaga o atual (e `reports/` e `data/` junto).
- **`relation does not exist`**: `make migrate`. Versão atual: `docker exec cai-postgres psql -U cai -d cai -c "SELECT version_num FROM alembic_version;"`.
- **O worker não pega job**: `docker logs cai-worker --tail 100` e `docker exec cai-redis redis-cli LLEN arq:queue`. Job na fila e worker parado costuma ser erro de import no início do worker.
- **O ZAP não responde**: `docker logs cai-zap --tail 50`. O container reinicia sozinho depois de morrer por falta de memória (`restart: unless-stopped`, teto de 6 GB).
- **`/` mostra o dashboard antigo**: esperado na stack de desenvolvimento. A tela web está na [seção 6](#6-a-tela-web).
- **`scripts/web_e2e.sh` sai com 2**: falta `orchestrator/web_dist`, ou o shield descartável não subiu (o script imprime o fim do log dele).
- **Um gate reprova**: leia o que ele imprimiu. Cada linha diz o arquivo e a regra.
- **Um scan falha ou volta vazio**: isso é o produto quebrando, não a stack. Veja [QUANDO-QUEBRA.md](QUANDO-QUEBRA.md).
