# Contribuindo com o RoqueShield

*Tradução de [CONTRIBUTING.md](../../CONTRIBUTING.md), a versão principal, em inglês. Se as duas divergirem, vale a em inglês.*

Obrigado por considerar uma contribuição. O RoqueShield ainda não chegou à 1.0 e ganha com issues, PRs, adapters de scanner novos, melhorias de prompt de IA, documentação e tradução.

Antes de abrir um PR, leia as seções abaixo: a maior parte das revisões trava em itens que estão documentados aqui.

## Código de Conduta

A participação é regida pelo [Código de Conduta](../../CODE_OF_CONDUCT.md) (em inglês). Ao contribuir, você concorda em cumpri-lo.

## Achou uma vulnerabilidade?

**Não** abra issue pública. Siga o [SECURITY.md](../../SECURITY.md) (em inglês) e use os GitHub Security Advisories.

## A regra do projeto

Regra sem mecanismo é decoração. Se você propõe uma norma, diga qual gate, teste ou script vai executá-la. E todo check novo nasce com mutante: quebre o código de propósito e mostre que o check reprova. Check que nunca reprovou não prova nada. Liste na descrição do PR os mutantes que você tentou.

## Jeitos de contribuir

- **Adapter de scanner novo**: a contribuição de maior impacto. Veja [Adicionar um adapter](#adicionar-um-adapter).
- **Correção de bug**: abra uma issue antes só se a correção não for trivial.
- **Funcionalidade**: abra uma issue no GitHub com o template *Feature Request* para discutir o desenho antes de codar.
- **Prompt de IA ou regra de triagem**: veja `orchestrator/ai/prompts/` e conte no PR o que você observou antes e depois.
- **Documentação ou tradução**: o mapa de todos os docs é o [INDEX.md](INDEX.md). Cada doc existe em inglês (`docs/`) e em português do Brasil (`docs/pt-BR/`); uma mudança entra nos dois, e o `scripts/check_docs_fresh.py` reprova doc sem o par ou com link quebrado.
- **Testes**: o piso do CI é 64% de cobertura e só sobe. Teste unitário para adapter e para router da API é sempre bem-vindo.

## Ambiente de desenvolvimento

O guia completo da stack de desenvolvimento (containers, portas, alvos do Make, a tela web, o CI) é o [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md). A versão curta:

Pré-requisitos:

- Python 3.13
- Docker Desktop (WSL2 no Windows) ou Docker Engine com Compose v2
- `make` (nativo no Linux e no macOS; no Windows use WSL)
- Pelo menos 8 GB de RAM livre (16 GB se você rodar o perfil `greenbone`)
- Uma GPU NVIDIA para o container `cai-ollama`, que o `make up` sobe; sem ela, suba os serviços pelo nome ([DESENVOLVIMENTO.md](DESENVOLVIMENTO.md#4-os-containers))

Clonar e preparar:

```bash
git clone https://github.com/roqueribeiro/roqueos-shield.git
cd roqueos-shield
cp .env.example .env
# Gere APP_TOKEN, ZAP_API_KEY e POSTGRES_PASSWORD, e ponha a mesma senha do Postgres
# no DATABASE_URL: o DESENVOLVIMENTO.md tem os comandos. A API se recusa a subir
# com o APP_TOKEN de exemplo.

make build       # as imagens do orchestrator, do kali-toolbox e do cai-expert
make up          # orchestrator, worker, postgres, redis, ollama, zap, trivy, kali-toolbox e o lab
make migrate     # alembic upgrade head
make smoke       # scan ativo no Juice Shop; o relatório HTML cai em reports/
```

O `make smoke` não julga o resultado: abra o relatório e confirme que ele tem achados reais de injeção. Zero achados no Juice Shop é reprovação.

### A tela web (`web/`)

A tela que a imagem standalone serve é um app Vue 3 + Quasar em `web/`. Use **yarn** (o lockfile é `yarn.lock`), nunca npm:

```bash
cd web
yarn install
yarn build            # escreve orchestrator/web_dist, que a API serve em /
cd .. && scripts/web_e2e.sh   # um shield descartável + o e2e da tela com Playwright
```

O `yarn dev` serve a tela na porta 9100 e repassa a API para 127.0.0.1:8080. Sem `orchestrator/web_dist`, a API recua para o dashboard antigo em `orchestrator/static/` (é o que a stack de desenvolvimento mostra). Os textos ficam em `web/src/i18n/`; os textos só do standalone (`shield.js`) existem em pt-BR, en-US e es-ES, e os outros idiomas recuam para o inglês neles. As capturas de tela da documentação são geradas pelo `scripts/doc_capturas.sh`, nunca à mão.

### A imagem standalone

```bash
docker build -f docker/images/orchestrator/Dockerfile -t roqueos-shield-engine:local .
docker build -f docker/images/standalone/Dockerfile --build-arg ENGINE=roqueos-shield-engine:local \
  -t roqueribeiro1988/roqueos-shield:dev-standalone .
ROQUESHIELD_VERSION=dev sh install.sh   # instala o seu build local, como um usuário instalaria
```

O `install.sh` tenta `docker pull` primeiro e, quando a tag não está no registro, usa a imagem que já está na sua máquina.

### Testes, lint e gates sem Docker

O `make test` e o `make lint` rodam dentro da imagem do orchestrator, que é buildada sem as dependências de desenvolvimento e sem `tests/`; use o ambiente local, do mesmo jeito que o CI:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check orchestrator tests scripts
.venv/bin/ruff format --check orchestrator tests scripts
.venv/bin/mypy orchestrator
python scripts/check_no_silence.py
python scripts/check_docs_fresh.py
python scripts/gen_diagrams.py --check
```

O que cada um segura, e o job do CI por trás, está no [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md#7-gates-locais). O que uma mudança tem que provar está no [CRITERIOS-DE-TESTE.md](CRITERIOS-DE-TESTE.md).

## Convenções de código

São cobradas na revisão e, a maioria, pelo CI:

- **Python 3.13**, type hints em tudo, `from __future__ import annotations` no topo de todo módulo
- **Async primeiro**: adapters, handlers da API e persistência são `async def`
- **Pydantic v2** para schemas, `SQLModel` para modelos do banco
- **structlog** para log (JSON em produção, texto em dev)
- **litellm** é a *única* entrada para qualquer LLM. **Não** importe `anthropic` nem `openai` direto.
- **Achados** são sempre `orchestrator.domain.schemas.Finding`. Sem variante por adapter.
- **Severidade** ajustada por contexto de IA vai em `Finding.ai_triage.adjusted_severity`. Nunca sobrescreva `Finding.severity`.
- **Datas** são sempre `datetime.now(UTC)` e gravadas com `sa_type=DateTime(timezone=True)`.
- **Zero achados tem que ser distinguível de "não rodou"**: o adapter levanta `ScanIntegrityError` ou declara uma lacuna de cobertura, nunca devolve vazio num erro. O `scripts/check_no_silence.py` reprova o merge se não for assim.

## Adicionar um adapter

Os adapters ficam em [`orchestrator/adapters/`](../../orchestrator/adapters/) e implementam o Protocol `ScannerAdapter` definido em [`base.py`](../../orchestrator/adapters/base.py). O guia passo a passo, com o que cada gate cobra em cada passo, é o [ESTENDER.md](ESTENDER.md).

Checklist mínimo de um adapter novo:

1. Implemente `health()`, `start_scan()`, `poll()`, `fetch_results()` e `normalize()`. O `poll()` lê o returncode, não só `task.done()`.
2. Normalize a saída bruta para o schema canônico `Finding` (`orchestrator/domain/schemas.py`).
3. Registre em `_build_adapters` e em `_SCANNER_ASSET_SUPPORT` (`orchestrator/jobs/pipelines.py`), ou em `orchestrator/jobs/exposure.py` se for OSINT, e declare as opções dele em `orchestrator/domain/opcoes.py`.
4. Adicione um teste unitário em `tests/unit/` montado sobre uma amostra real da saída do scanner, cobrindo os dois lados: ele acha, e saída ausente ou ilegível levanta em vez de devolver vazio. Nada de chamada de rede real em teste.
5. Atualize a tabela de adapters do [`README.md`](../../README.md) e do [`README.pt-BR.md`](../../README.pt-BR.md), e a [ARQUITETURA.md](ARQUITETURA.md) com o par em inglês.
6. Ponha o binário em `docker/images/orchestrator/Dockerfile` (é o worker que roda os scanners), com versão pinada. Chave ou URL é campo de `Settings` em `orchestrator/config.py` e entra no `.env.example`; nunca fixe no código.

Se você usa o Claude Code, a skill [`cai-add-adapter`](../../.claude/skills/cai-add-adapter/SKILL.md) monta parte disso. O template de `poll()` dela decide só por `task.done()` e reprova no gate do silêncio: para essa peça, siga o [ESTENDER.md](ESTENDER.md).

## Mexendo em áreas sensíveis

Alguns arquivos têm exigência extra de revisão porque afetam a postura de compliance e de segurança:

- **`orchestrator/domain/scrubber.py`**: mudança de regex precisa de justificativa na descrição do PR. Não afrouxe padrão sem explicar o falso positivo que motivou a mudança.
- **`orchestrator/audit/logger.py`**: o log de auditoria é append-only. Nunca introduza caminho de código que faça `UPDATE` ou `DELETE` em `audit_log`. O trigger do Postgres é rede de proteção, não licença para afrouxar a camada da aplicação.
- **`orchestrator/api/deps.py`**: código de autenticação. Nunca remova `require_token` de um endpoint que já o tem. Discuta o desenho numa issue antes.

## Fluxo de PR

1. Faça fork do repositório e crie uma branch a partir da `main`. Dê um nome que descreva (`adapter/wapiti`, `fix/zap-timeout`, `docs/en-translation`).
2. Faça commits focados. Evite juntar refatoração com funcionalidade.
3. Adicione ou atualize testes.
4. Atualize o [`CHANGELOG.md`](../../CHANGELOG.md) em `[Unreleased]`. Use as categorias: Added / Changed / Deprecated / Removed / Fixed / Security.
5. Assine os commits com uma [linha DCO `Signed-off-by:`](https://developercertificate.org/) (`git commit -s`). Ela afirma que você escreveu a mudança e pode submetê-la sob Apache 2.0.
6. Abra o PR usando o template. Preencha o checklist.
7. O CI tem que estar verde. Responda aos comentários da revisão com commits adicionais: o merge é squash, então histórico local bagunçado não tem problema.

## Labels de triagem de issue

- `good first issue`: pequena, bem delimitada, pede pouco contexto
- `help wanted`: queremos muito um PR
- `adapter`: adicionar ou melhorar uma integração de scanner
- `ai`: qualquer coisa em `orchestrator/ai/`
- `compliance`: scrubber, log de auditoria, allowlist, lógica de auth-ref
- `docs`: qualquer coisa em `docs/`, os READMEs e este arquivo
- `breaking`: mexe numa API pública ou numa migration do banco

## Release (só mantenedores)

1. Suba a versão no [`pyproject.toml`](../../pyproject.toml), em `orchestrator/__init__.py`, em `web/package.json` e no `VERSAO_PADRAO` do `install.sh` (o `scripts/check_docs_fresh.py` reprova se discordarem).
2. Mova os itens de `[Unreleased]` do [`CHANGELOG.md`](../../CHANGELOG.md) para a versão nova, com data.
3. Tag: `git tag -s vX.Y.Z -m "vX.Y.Z"` (tag assinada). O `scripts/release-docker.sh` se recusa a publicar se a tag `vX.Y.Z` não existir, não bater com a versão do `pyproject.toml` ou não apontar para o `HEAD`, com a árvore limpa.
4. Publique as imagens com o `scripts/release-docker.sh` **antes** do merge do bump: o `install.sh` da `main` instala a versão que ele cita, então essa imagem tem que existir no Docker Hub antes.
5. `git push --tags`, depois crie um GitHub Release a partir da tag com a seção do CHANGELOG no corpo.

## Dúvidas?

Abra uma issue. Para questão de desenho, descreva o problema antes da solução.
