# RoqueShield (motor `cai`): comandos da stack de desenvolvimento.
#
# Targets principais (`make help` lista todos):
#   make up          - sobe orchestrator + worker + db + redis + scanners + lab
#   make api         - sobe orchestrator + worker + db + redis (sem scanners nem lab)
#   make ollama-up   - sobe o Ollama local (pede GPU NVIDIA; fora do default)
#   make down        - desce tudo, de todos os profiles (sem apagar volumes)
#   make build       - rebuild das imagens
#   make scan TARGET=... - scan síncrono pela CLI, dentro do container (sem fila)
#   make scan-api TARGET_ID=... - dispara via API REST (assíncrono)
#   make exposure    - scan OSINT/Exposure externa
#   make smoke       - smoke test E2E
#   make migrate     - alembic upgrade head
#   make test        - pytest, local (uv), não no container
#   make lint        - ruff check + ruff format --check, local (uv)

SHELL := /usr/bin/env bash

# --env-file e --project-directory garantem que o .env da raiz seja lido e que os
# caminhos `../` dos compose resolvam a partir de docker/, mesmo com -f docker/...
COMPOSE_FLAGS := --env-file .env --project-directory docker
COMPOSE_BASE := docker compose $(COMPOSE_FLAGS) -f docker/compose.yml
COMPOSE_FULL := $(COMPOSE_BASE) -f docker/compose.scanners.yml -f docker/compose.lab.yml
COMPOSE_GREENBONE := $(COMPOSE_BASE) -f docker/compose.greenbone.yml
COMPOSE_OBS := $(COMPOSE_BASE) -f docker/compose.observability.yml
COMPOSE_AGENT := $(COMPOSE_BASE) -f docker/compose.agent.yml
COMPOSE_PROXY := $(COMPOSE_BASE) -f docker/compose.proxy.yml
# Todos os arquivos: o `down` só derruba serviço de arquivo que ele recebeu. Antes o
# greenbone e o proxy ficavam de fora, e os containers deles sobreviviam ao `make down`.
COMPOSE_ALL := $(COMPOSE_FULL) -f docker/compose.greenbone.yml -f docker/compose.observability.yml \
               -f docker/compose.agent.yml -f docker/compose.proxy.yml

PROFILES_FULL := --profile default --profile scanners --profile lab
PROFILES_API := --profile default
PROFILES_ALL := $(PROFILES_FULL) --profile ollama --profile greenbone --profile obs \
                --profile ai-agent --profile proxy

# A imagem do orchestrator tem `entrypoint: uvicorn` no compose. Comando da CLI precisa
# trocar o entrypoint, senão `run orchestrator scan ...` vira `uvicorn scan ...`.
CLI := run --rm --entrypoint python orchestrator -m orchestrator.cli

# Testes e lint rodam no checkout, não na imagem: a imagem não leva tests/ nem as
# dependências de dev (o Dockerfile instala com --no-dev).
UV_RUN := uv run --frozen --extra dev

TARGET ?= http://juice-shop:3000
TARGET_ID ?=
AUTH_REF ?=
ARGS ?=

.PHONY: help build up api down logs ps shell scan scan-api scan-no-ai smoke ollama-up \
        ollama-pull migrate revision test lint typecheck exposure greenbone-up \
        greenbone-down obs-up agent-up backup proxy-up clean

help: ## lista de comandos
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F ':.*?## ' '{printf "  %-20s %s\n", $$1, $$2}'

build: ## rebuild das imagens (orchestrator/worker e kali-toolbox; cai-expert opcional)
	$(COMPOSE_FULL) build orchestrator worker
	$(COMPOSE_FULL) build kali-toolbox
	$(COMPOSE_AGENT) build cai-expert || echo "aviso: cai-expert não buildou (opcional, profile ai-agent)" >&2

up: ## sobe stack de dev (orchestrator + worker + db + redis + scanners + lab)
	$(COMPOSE_FULL) $(PROFILES_FULL) up -d
	@echo ""
	@echo "Stack no ar:"
	@echo "  orchestrator API : http://127.0.0.1:8080  (X-API-Token: \$$APP_TOKEN)"
	@echo "  zap              : http://127.0.0.1:8090"
	@echo "  trivy            : http://127.0.0.1:4954"
	@echo "  juice-shop       : http://127.0.0.1:3000"
	@echo "  dvwa             : http://127.0.0.1:8000"
	@echo "  webgoat          : http://127.0.0.1:8081"
	@echo "Ollama local é à parte: make ollama-up (GPU NVIDIA) ou o Ollama nativo do host."

api: ## sobe orchestrator + worker + db + redis (sem scanners externos nem lab)
	$(COMPOSE_BASE) $(PROFILES_API) up -d
	@echo ""
	@echo "API no ar: http://127.0.0.1:8080/health"

ollama-up: ## sobe o Ollama local (reserva GPU NVIDIA; sem GPU, use o Ollama nativo)
	$(COMPOSE_BASE) --profile ollama up -d ollama
	@echo "Ollama: http://127.0.0.1:11434  (modelos: make ollama-pull)"

down: ## desce tudo, todos os profiles (volumes ficam)
	$(COMPOSE_ALL) $(PROFILES_ALL) down

logs: ## logs do orchestrator e do worker
	$(COMPOSE_FULL) logs -f orchestrator worker

ps: ## status dos containers
	$(COMPOSE_FULL) ps

shell: ## shell no orchestrator
	$(COMPOSE_FULL) run --rm --entrypoint /bin/bash orchestrator

scan: ## scan síncrono pela CLI (TARGET=url, AUTH_REF=ticket se REQUIRE_AUTH_REF=true)
	$(COMPOSE_FULL) $(CLI) scan "$(TARGET)" --asset-type url --criticality medium \
		$(if $(AUTH_REF),--authorization-ref "$(AUTH_REF)") $(EXTRA)

scan-api: ## dispara scan via API REST (TARGET_ID=uuid; scanners pelo asset_type do alvo)
	@if [ -z "$(TARGET_ID)" ]; then echo "use TARGET_ID=<uuid>"; exit 1; fi
	curl -fsS -X POST http://127.0.0.1:8080/scans \
		-H "Content-Type: application/json" \
		-H "X-API-Token: $${APP_TOKEN:-dev-changeme}" \
		-d '{"target_id":"$(TARGET_ID)"$(if $(AUTH_REF),$(comma)"authorization_ref":"$(AUTH_REF)")}'

scan-no-ai: ## scan sem triagem AI (não precisa de chave de LLM)
	$(COMPOSE_FULL) $(CLI) scan "$(TARGET)" --asset-type url --skip-ai \
		$(if $(AUTH_REF),--authorization-ref "$(AUTH_REF)") $(EXTRA)

exposure: ## scan OSINT/Exposure externa: make exposure COMPANY="Acme" EXTRA="--domains acme.com"
	@test -n "$(COMPANY)" || { echo 'falta COMPANY: make exposure COMPANY="Acme" EXTRA="--domains acme.com"'; exit 2; }
	$(COMPOSE_FULL) $(CLI) exposure "$(COMPANY)" $(EXTRA)

smoke: ## E2E: sobe lab e roda scan no Juice Shop
	@bash scripts/smoke.sh

migrate: ## alembic upgrade head
	$(COMPOSE_FULL) run --rm --entrypoint alembic orchestrator upgrade head

revision: ## cria nova migração (NAME=description)
	@if [ -z "$(NAME)" ]; then echo "use NAME=description"; exit 1; fi
	$(COMPOSE_FULL) run --rm --entrypoint alembic orchestrator revision --autogenerate -m "$(NAME)"

test: ## pytest local via uv (ARGS=tests/unit/test_x.py para um alvo)
	$(UV_RUN) pytest -q $(if $(ARGS),$(ARGS),tests/)

lint: ## ruff check + ruff format --check, como o CI (orchestrator, tests, scripts)
	$(UV_RUN) ruff check orchestrator tests scripts
	$(UV_RUN) ruff format --check orchestrator tests scripts

typecheck: ## mypy (no CI ainda não bloqueia o merge)
	$(UV_RUN) mypy orchestrator

ollama-pull: ## baixa modelos default no Ollama
	@bash scripts/ollama-bootstrap.sh

greenbone-up: ## sobe stack Greenbone (CUIDADO: feed sync 30min-3h, ~5GB)
	$(COMPOSE_GREENBONE) --profile greenbone up -d
	@echo "Greenbone subindo. Acompanhe sync com: docker logs cai-gvm-feeds -f"
	@echo "GSA web: http://127.0.0.1:9392 (admin/admin). TROQUE a senha após o feed sync."

greenbone-down: ## desce stack Greenbone
	$(COMPOSE_GREENBONE) --profile greenbone down

obs-up: ## sobe Phoenix tracing
	$(COMPOSE_OBS) --profile obs up -d
	@echo "Phoenix UI: http://127.0.0.1:6006"

agent-up: ## sobe cai-expert (profile ai-agent)
	$(COMPOSE_AGENT) --profile ai-agent up -d

proxy-up: ## sobe Caddy TLS reverse proxy
	$(COMPOSE_PROXY) --profile proxy up -d
	@echo "Caddy: https://cai.local/ (mapear cai.local para 127.0.0.1 no /etc/hosts)"

backup: ## backup do Postgres (a trilha de auditoria vai junto, é tabela dele) + reports/
	@bash scripts/backup.sh

clean: ## desce tudo e APAGA volumes, reports/ e data/ (CUIDADO: apaga dados)
	$(COMPOSE_ALL) $(PROFILES_ALL) down -v
	rm -rf reports/* data/*

comma := ,
