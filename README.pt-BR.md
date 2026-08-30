<div align="center">

<img src="docs/assets/logo-roqueos.png" alt="RoqueOS" width="96" />

# RoqueShield

**Teste de segurança contínuo que se recusa a ficar calado.**

Quinze scanners atrás de um contrato de adapter, triagem por LLM sobre evidência
higienizada, um agente que confirma o achado dentro de um Kali sob coleira, e um
**AI Fix Bundle** que outro agente consome para corrigir o código.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/release/python-3130/)
[![CI](https://github.com/roqueribeiro/roqueos-shield/actions/workflows/ci.yml/badge.svg)](https://github.com/roqueribeiro/roqueos-shield/actions/workflows/ci.yml)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#status)

[English](README.md) · [Modelo C4](docs/c4-model.pt-BR.md) · [Integrações](docs/integrations.pt-BR.md) · [Arquitetura](docs/architecture.md)

</div>

---

## Por que isto existe

Um scanner quebrado e um alvo limpo produzem **exatamente a mesma saída: zero
achados.** Num relatório que vai para a auditoria de um banco, essa é a única
diferença que importa — e era a diferença que esta ferramenta não sabia fazer.

Nove adapters tinham a mesma forma de defeito: exceção engolida, report vazio lido
como `{}`, um `poll()` que chamava de "concluído" um processo morto, um scanner que
recebia URL onde esperava diretório. Todos fechavam o scan com zero achados e um
tique verde.

Daí a regra que governa o projeto, e os dois gates de CI que a executam:

> **Zero achados aqui significa *limpo*, ou significa *não rodou*?
> Se não houver como distinguir, falta um sinal.**

Todo o resto deste repositório existe para servir a essa frase.

---

## O sistema em uma figura

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/diagrams/c1-context-dark.svg">
  <img alt="Contexto do sistema" src="docs/assets/diagrams/c1-context-light.svg">
</picture>

Mais quatro níveis de detalhe — containers, componentes, ciclo de vida do adapter,
infraestrutura, esteira do scan, o Kali com o agente e as telas — em
**[docs/c4-model.pt-BR.md](docs/c4-model.pt-BR.md)**.

---

## O que faz

| Etapa | O que acontece | Onde |
| --- | --- | --- |
| **Scan** | A ferramenta certa para o tipo de alvo. Semgrep lê o código-fonte; Gitleaks e Trufflehog caçam segredo; Trivy cobre CVE em imagem e dependência; Checkov cobre IaC; ZAP e Nuclei sondam a aplicação no ar; Nmap e Greenbone cobrem a rede. | `orchestrator/adapters/` |
| **Dedupe** | Fusão determinística por `deduped_key`, mantendo a maior severidade. Credencial rotacionada não colapsa em um achado só, porque o fingerprint discrimina. | `orchestrator/domain/dedup.py` |
| **Triagem** | Um LLM reordena severidade, marca falso positivo provável, mapeia OWASP e CWE e propõe remediação — sobre evidência que o scrubber de PII/PCI limpou antes. | `orchestrator/ai/analyzer.py` |
| **Investigação** | Sob demanda, um agente ReAct pega **um** achado e tenta confirmá-lo: roda ferramenta de verdade no Kali, lê a saída, decide o próximo passo. Todo comando passa pela coleira antes. | `orchestrator/ai/agentic/` |
| **Entrega** | Um **AI Fix Bundle** — id estável, prioridade, arquivo e linha, pista de stack, passos de verificação — que Claude Code, Cursor ou um passo de CI consome para propor o patch. | `orchestrator/reporting/exporters/` |

### A esteira, fase a fase

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/diagrams/esteira-scan-dark.svg">
  <img alt="A esteira de um scan" src="docs/assets/diagrams/esteira-scan-light.svg">
</picture>

---

## A coleira é a parte que importa

Se você pretende apontar isto para alguma coisa real, leia esta seção antes do
quickstart.

O escopo do agente **não é uma frase no prompt.** Prompt não restringe processo que
tem shell. É código em
[`orchestrator/ai/agentic/executor.py`](orchestrator/ai/agentic/executor.py),
conferido antes de cada comando: allowlist por fase, alvo validado pelo mesmo
validador que os scanners usam, `argv` entregue como **lista** ao
`asyncio.create_subprocess_exec` — nunca shell, então não existe metacaractere para
escapar — recusa de flag que escreve em disco, timeout duro, um modo `lab_only` que
vem **ligado**, e um `dry_run` que planeja e audita sem executar. Toda decisão,
inclusive toda recusa, vai para a trilha por `ExecDecision.to_audit()`.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/diagrams/kali-cai-agente-dark.svg">
  <img alt="Kali toolbox e a coleira do agente" src="docs/assets/diagrams/kali-cai-agente-light.svg">
</picture>

**O que ainda não é, dito aqui para ninguém descobrir em produção:** o container
`cai-expert` é um stub declarado — o Dockerfile termina a instalação com `|| true` e
o compose diz isso no próprio cabeçalho — e `_cai_framework_available()` hoje devolve
apenas `bool(settings.AGENT_ENABLED)`, sem conferir se o framework está mesmo
instalado. O executor e a coleira são reais e testados; o container empacotado do
agente, não.

---

## Quickstart

Pré-requisitos: Docker Desktop (WSL2 no Windows) ou Docker Engine, 8 GB de RAM livre,
e opcionalmente uma chave Anthropic/OpenAI — ou nenhuma, se apontar para um modelo
local.

```bash
git clone https://github.com/roqueribeiro/roqueos-shield.git
cd roqueos-shield
cp .env.example .env
# preencha APP_TOKEN, POSTGRES_PASSWORD, ZAP_API_KEY (strings aleatórias)
# opcional: ANTHROPIC_API_KEY ou OPENAI_API_KEY

make build       # constrói a imagem do orchestrator
make up          # postgres + redis + orchestrator + worker + zap + alvos de lab
make migrate     # alembic upgrade head
make smoke       # ponta a ponta: varre o Juice Shop e produz um relatório HTML
```

Depois, `http://127.0.0.1:8080/ui/` para o dashboard, ou `/docs` para o OpenAPI.

**Soberania de dado é um interruptor, não uma esperança.** Com modelo local (Ollama
ou LM Studio) e `ALLOW_CLOUD_FALLBACK=false`, um modelo local que falha faz o scan
falhar, em vez de mandar seus achados para um provedor na nuvem.

---

## Dentro do RoqueOS

O RoqueShield também é um app de primeira classe dentro do
[RoqueOS](https://roqueos.com.br): admin-only, provisionado em container, com stepper
de scan ao vivo por SSE, configuração guiada de provedor de IA, trilha de auditoria
imutável e segredo cifrado em AES. O roqueos-server provisiona a stack inteira por
Docker e faz proxy reverso da API injetando o token server-side — **o browser nunca
vê a credencial.**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/diagrams/telas-roqueos-dark.svg">
  <img alt="Telas do RoqueShield dentro do RoqueOS" src="docs/assets/diagrams/telas-roqueos-light.svg">
</picture>

> A figura acima é **diagrama de interface, não captura de tela.**

---

## Plugando em agente, API e esteira

Três superfícies existem hoje, e elas bastam para fechar o laço
scan → conserto → re-scan sem humano no meio:

| Superfície | Entrada | Boa para |
| --- | --- | --- |
| **CLI** | `cai scan` · `cai exposure` · `cai bundle` | agente que já tem shell — Claude Code, Cursor, passo de CI |
| **REST** | 33 rotas, OpenAPI em `/docs`, SSE em `/ui/api/events` | serviço integrando pela rede |
| **AI Fix Bundle** | `GET /reports/{scan_id}/ai-bundle`, schema `1.0.0` | o agente que escreve o patch |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/diagrams/integracoes-agente-dark.svg">
  <img alt="Superfícies de integração e o laço do agente" src="docs/assets/diagrams/integracoes-agente-light.svg">
</picture>

O critério de parada não é "o agente disse que acabou". É o **scan seguinte** não
achar o que o anterior achou, com `coverage_complete` ainda verdadeiro. Scanner que
deixou de rodar entre as rodadas invalida os dois — e aparece em `scanners_skipped`
em vez de virar zero achados.

Um **servidor MCP** e uma **GitHub Action reutilizável** estão desenhados em
[docs/integrations.pt-BR.md](docs/integrations.pt-BR.md) e **não estão
implementados**. Estão marcados como roadmap na figura acima, e você não vai
encontrá-los no código.

---

## Adapters

Quinze adapters implementam um `ScannerAdapter` Protocol. Nove são alcançáveis pela
factory do scan; outros seis são instanciados direto pela trilha OSINT.

| Adapter | Scanner | Tipo | Ligado por |
| --- | --- | --- | --- |
| `semgrep_adapter` | Semgrep | **SAST** — lê o código-fonte | factory |
| `nmap_adapter` | Nmap | Rede | factory |
| `zap_adapter` | OWASP ZAP | Aplicação web (DAST) | factory |
| `nuclei_adapter` | Nuclei | Scan por template | factory |
| `trivy_adapter` | Trivy | Container / IaC / FS | factory |
| `checkov_adapter` | Checkov | Má configuração de IaC | factory |
| `gitleaks_adapter` | Gitleaks | Segredo | factory · OSINT |
| `trufflehog_adapter` | Trufflehog | Segredo verificado | factory · OSINT |
| `greenbone_adapter` | Greenbone / OpenVAS | Vulnerabilidade de rede | factory |
| `dnstwist_adapter` | dnstwist | Typosquatting | OSINT |
| `subdomain_takeover_adapter` | subfinder + httpx + nuclei | Subdomain takeover | OSINT |
| `shodan_adapter` | Shodan | Exposição na internet | OSINT |
| `github_exposure_adapter` | GitHub Search | Vazamento em código | OSINT |
| `censys_adapter` | Censys | Exposição na internet | **não ligado** |
| `kube_bench_adapter` | kube-bench | CIS Kubernetes | **não ligado** |

Os dois últimos são contabilidade honesta: estão implementados e têm teste unitário,
e **nenhum caminho de produção os constrói hoje** — nem `_build_adapters()` nem a
trilha OSINT os referencia. Versões anteriores desta tabela os listavam como se
rodassem.

---

## O que segura a honestidade

| Situação | O que o adapter faz | O que o relatório diz |
| --- | --- | --- |
| Rodou e não achou | devolve `[]` | achado nenhum, cobertura completa |
| Não deu para verificar | levanta `ScanIntegrityError` | entra em `scanners_skipped`, `coverage_complete: false` |
| Verificou em parte | preenche `RawResults.coverage_gaps` | um achado **INFO** nomeando a lacuna |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/diagrams/c4-code-dark.svg">
  <img alt="Ciclo de vida do adapter e o contrato do silêncio" src="docs/assets/diagrams/c4-code-light.svg">
</picture>

Dois gates de CI seguram as duas metades dessa promessa, e **os dois foram validados
por teste de mutação** — quebrando o código de propósito e confirmando que o gate
reprova:

- **`silencio`** ([`scripts/check_no_silence.py`](scripts/check_no_silence.py)) lê a
  AST dos adapters e reprova `except` no ciclo de vida do scan que termina em
  resultado vazio, `poll()` que decide por `task.done()` sem ler `task.result()`, e
  payload de sucesso fabricado. `# silencio-ok: motivo` é a única passagem — e o
  motivo escrito é o que denuncia se um dia um silêncio de verdade for liberado.
- **`efetividade`** (`tests/integration/test_efetividade_e2e.py`) monta um
  repositório com defeitos conhecidos — injeção de comando, SQLi por taint, `pickle`,
  MD5, Flask `debug=True`, bucket S3 público, security group `0.0.0.0/0`, disco sem
  cifra — roda o pipeline inteiro e exige achado real de cada camada, conferindo que
  scanner ausente aparece como pulado. Sem ele, uma ferramenta que só levantasse
  exceção passaria em todo o resto, porque "zero achados" é a saída natural de um
  scanner quebrado.

**E o gate tem gate.** Uma auditoria adversarial burlou a primeira versão de quatro
formas e reintroduziu o silêncio no adapter do nmap com o CI verde. Um controle que o
autor contorna em quatro tentativas não é controle. As quatro viraram
`tests/unit/test_gate_do_silencio.py`, e o gate foi endurecido contra cada uma.

A regra completa, com os nove casos históricos que a produziram, está em
[`.claude/rules/60-contrato-do-silencio.md`](.claude/rules/60-contrato-do-silencio.md).

### SAST funciona com egress fechado

O `--config auto` do Semgrep é incompatível com o `--metrics off` que este projeto
usa por soberania de dado, e os pacotes `p/...` são baixados do registro a cada scan
— o que silenciosamente resulta em **zero regras** numa rede corporativa restrita,
que é o ambiente normal do alvo desta ferramenta. Por isso a imagem embarca o
conjunto `semgrep-rules` (LGPL-2.1) em `/opt/semgrep-rules`, pinado por commit e
validado no build, e o adapter carrega só os diretórios de linguagem presentes.
Aponte `SEMGREP_RULES_DIR` para outro lugar se quiser regra própria.

O Nuclei recebe o mesmo tratamento pelo outro lado: o build conta os templates e
**falha abaixo do piso de 2000**, porque imagem que sobe sem template é um scanner
que não acha nada e não avisa.

---

## Implantação

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/diagrams/infra-deploy-dark.svg">
  <img alt="Infraestrutura e implantação" src="docs/assets/diagrams/infra-deploy-light.svg">
</picture>

Dois caminhos, uma imagem: o roqueos-server provisiona a stack e **não publica porta
nenhuma** no host, ou o `docker compose` sobe com a `8080` publicada para trabalho
local. Portas, volumes e profiles em [docs/runbook.md](docs/runbook.md).

---

## Estrutura do projeto

```
roqueos-shield/
├── CLAUDE.md                    # overview para o Claude Code
├── README.md / README.pt-BR.md
├── docs/
│   ├── c4-model.md              # os nove diagramas, nível a nível (EN)
│   ├── integrations.md          # CLI, REST, bundle, laço do agente (EN)
│   ├── architecture.md          # arquitetura detalhada (pt-BR)
│   ├── usage.md                 # cookbook (pt-BR)
│   ├── runbook.md               # operação dia a dia (pt-BR)
│   ├── threat-model.md
│   ├── ai-fix-bundle-spec.md
│   └── assets/                  # logo + os 18 SVGs gerados
├── orchestrator/
│   ├── main.py                  # FastAPI + StaticFiles da UI
│   ├── cli.py                   # cai scan/exposure/serve/bundle
│   ├── config.py                # pydantic-settings
│   ├── adapters/                # 15 ScannerAdapters + base.py + _cleanup.py
│   ├── ai/
│   │   ├── gateway.py           # litellm + telemetria em AIRun
│   │   ├── analyzer.py          # triage_batch
│   │   ├── agentic/             # executor (a coleira) + cai_expert (o laço)
│   │   └── prompts/
│   ├── api/routers/             # 10 routers, 33 rotas
│   ├── domain/                  # Finding canônico, scrubber, dedup, validador
│   ├── jobs/                    # workers arq + pipelines + fases
│   ├── persistence/             # SQLModel, 9 tabelas, 7 migrations
│   ├── reporting/               # HTML, compliance, coverage, exporters
│   └── static/                  # dashboard HTML+CSS+JS, sem build
├── docker/
│   ├── compose.yml + 6 arquivos de profile
│   └── images/{orchestrator,kali-toolbox,cai-expert}/Dockerfile
├── tests/                       # 302 funções de teste; gate de cobertura em 64 %
├── scripts/
│   ├── check_no_silence.py      # o gate do contrato do silêncio (AST)
│   ├── check_docs_fresh.py      # doc x código
│   ├── gen_diagrams.py          # regenera os 18 SVGs
│   └── diagrams/                # os diagramas como código
└── .claude/                     # 10 skills + 13 commands + rules
```

*(Esta árvore substitui uma versão anterior que dizia 14 adapters, 8 routers e 3
migrations. Eram 15, 10 e 7 — a árvore tinha envelhecido calada, que é exatamente o
problema que o `check_docs_fresh.py` existe para pegar.)*

---

## Limitações conhecidas

- **Três números de versão diferentes** — `pyproject.toml` diz `0.1.0`, o `main.py`
  diz `0.4.0`, e o AI Fix Bundle emite `"version": "0.3.0"`. Quem consome o bundle
  não consegue dizer qual build o produziu.
- **`render_pdf()` não tem chamador** — o extra `[pdf]` instala o WeasyPrint e nada
  o invoca. PDF e CSV que aparecem na tela do RoqueShield são montados no front.
- **`cai-expert` é stub** — o fallback funciona; a integração completa com o
  `cai-framework`, não.
- **Dashboard sem auth visual** — token por `?token=...` na URL ou localStorage.
  OIDC segue como TODO.
- **Log ao vivo reinicia com o processo** — ring buffer em memória; o histórico fica
  no `docker logs`.
- **Feed inicial do Greenbone** leva de 30 min a 3 h e ocupa ~5 GB.
- **UI sem tratamento mobile** — funciona em desktop.
- **Cancelamento de scan** por `DELETE` REST; WebSocket bidirecional não existe.
- **E2E de UI** — só smoke manual no browser.
- **Modelos de raciocínio** (Qwen 3.x, DeepSeek-R1) consomem `max_tokens` dentro de
  `<think>`; suba para 8192+ se a saída vier vazia.

---

## Documentação

| Documento | Idioma | O que cobre |
| --- | --- | --- |
| [docs/c4-model.pt-BR.md](docs/c4-model.pt-BR.md) | pt-BR | os nove diagramas, nível a nível |
| [docs/integrations.pt-BR.md](docs/integrations.pt-BR.md) | pt-BR | CLI, REST, bundle, laço do agente, roadmap |
| [docs/architecture.md](docs/architecture.md) | pt-BR | layout interno, fluxos, segurança e compliance |
| [docs/usage.md](docs/usage.md) | pt-BR | receitas ponta a ponta |
| [docs/runbook.md](docs/runbook.md) | pt-BR | operação, troubleshooting, armadilhas |
| [docs/threat-model.md](docs/threat-model.md) | pt-BR | atores, cenários, mitigações |
| [docs/ai-fix-bundle-spec.md](docs/ai-fix-bundle-spec.md) | pt-BR | o contrato do bundle, schema 1.0.0 |

### Regerando os diagramas

Toda figura desta documentação é gerada a partir de código em
[`scripts/diagrams/`](scripts/diagrams/), não desenhada à mão:

```bash
python scripts/gen_diagrams.py           # regenera os 18 SVGs
python scripts/gen_diagrams.py --check   # CI: reprova se algum estiver atrasado, faltando ou órfão
```

Diagrama que só existe como imagem morre no primeiro refactor: ninguém sabe refazer,
e ele vira uma foto antiga da arquitetura pendurada no README. O `--check` é o que
impede isso, e ele está no CI.

---

## Sobre o nome

O produto é **RoqueShield**. O pacote Python ainda é `cai-orchestrator`, o comando
ainda é `cai`, e os containers ainda carregam o prefixo `cai-`. Isso é deliberado por
enquanto: a imagem publicada no Docker Hub e toda instalação existente do RoqueOS
referenciam os nomes antigos, e renomear sem caminho de migração quebraria a stack no
próximo `install.sh --update`. A renomeação está registrada, não esquecida.

## Contribuindo

Issues e PRs são bem-vindos — leia [CONTRIBUTING.md](CONTRIBUTING.md) e o
[Código de Conduta](CODE_OF_CONDUCT.md) antes. Para relato de segurança, siga o
[SECURITY.md](SECURITY.md) (canal privado).

## Licença

Apache License 2.0 — veja [LICENSE](LICENSE) e [NOTICE](NOTICE). O RoqueShield
embarca ou invoca software de terceiros sob as respectivas licenças; veja `NOTICE` e
`pyproject.toml`.
