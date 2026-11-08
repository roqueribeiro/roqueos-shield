# Glossário

*Tradução de [GLOSSARY.md](../GLOSSARY.md), a versão principal, em inglês. Se as duas divergirem, vale a em inglês.*

As CLIs, a API e o código imprimem e nomeiam muita coisa em português; outras ficam em inglês, como no código. Quando o termo aparece nas duas línguas, as duas estão aqui.

## Glossário

| Termo | O que é aqui | Onde ver mais |
| --- | --- | --- |
| **RoqueShield** | O produto: teste contínuo de segurança com triagem de IA, para ambiente regulado | [../../README.pt-BR.md](../../README.pt-BR.md) |
| **Motor** (`cai`) | O nome interno do motor que roda os scans: pacote `cai-orchestrator`, containers `cai-*`, CLI de administração `cai`. É o mesmo software do RoqueShield, com o nome antigo | [REFERENCIA.md](REFERENCIA.md#3-a-cli-de-administração-cai) |
| **Standalone** | A imagem de um container só (`roqueribeiro1988/roqueos-shield:<versão>-standalone`) com API, worker, Redis, ZAP e a tela, que o `install.sh` sobe | [REFERENCIA.md](REFERENCIA.md#1-o-instalador-installsh) |
| **Supervisor** | O PID 1 do container standalone (`orchestrator/standalone/supervisor.py`): gera os segredos, sobe Redis, ZAP, API e worker, reinicia quem cair | [REFERENCIA.md](REFERENCIA.md#10-arquivos-e-volumes) |
| **Código de primeiro uso** (`SETUP_CODE`) | O código que o `POST /setup` exige para criar o primeiro admin. Gerado em `/data/secrets/SETUP_CODE`; o instalador põe ele no fragmento da URL, que nunca chega ao servidor | [REFERENCIA.md](REFERENCIA.md#1-o-instalador-installsh) |
| **Token de serviço** (`APP_TOKEN`) | O token que vale o principal de serviço `admin` (`service@local`). O boot recusa valor de exemplo | [REFERENCIA.md](REFERENCIA.md#4-api-rest) |
| **Token de usuário** | Token por usuário mandado no `X-API-Token`, guardado como SHA-256 e mostrado uma vez. É como a CLI, o CI e o MCP se autenticam | [REFERENCIA.md](REFERENCIA.md#4-api-rest) |
| **Papel** e **permissão** | Quatro papéis (`admin`, `operator`, `auditor`, `viewer`), cada um um conjunto fixo das cinco permissões (`users:manage`, `scans:run`, `scans:read`, `audit:read`, `config:manage`) | [REFERENCIA.md](REFERENCIA.md#9-papéis-e-permissões) |
| **Alvo** e **tipo de alvo** (`asset_type`) | Para onde o scan aponta, registrado com `POST /targets`. Tipos: `url`, `domain`, `host`, `port`, `image`, `repo`, `k8s_resource` | [REFERENCIA.md](REFERENCIA.md#8-perfis-de-scan) |
| **Escopo** | O conjunto de alvos que a instância está autorizada a testar: `LAB_ONLY`, mais a allowlist, mais o `REQUIRE_AUTH_REF`. Conferido quando o alvo é registrado e de novo quando o scan começa | [OPERACAO.md](OPERACAO.md) |
| **Allowlist** (`TARGET_ALLOWLIST`) | A lista escrita de alvos autorizados: hostnames, IPs, CIDRs, `*.dominio`. Vazia por padrão | [REFERENCIA.md](REFERENCIA.md#6-variáveis-de-ambiente) |
| **`LAB_ONLY`** | Ligado por padrão. Bloqueia endereço privado, loopback, link-local e de metadados de nuvem que não esteja na allowlist. Loopback e metadados seguem bloqueados mesmo com ele desligado | [REFERENCIA.md](REFERENCIA.md#6-variáveis-de-ambiente) |
| **`authorization_ref`** | A referência à autorização escrita de um scan (ticket, mudança). Vai para a trilha de auditoria; obrigatória com `REQUIRE_AUTH_REF=true` e sempre no `start_scan` do MCP | [REFERENCIA.md](REFERENCIA.md#4-api-rest) |
| **Trilha de auditoria** (`audit_log`) | Toda ação sensível (scan criado ou apagado, login, primeiro uso, investigação e seus comandos, ajustes) registrada antes de acontecer. Append-only no Postgres por trigger; editável no SQLite, que o `REQUIRE_IMMUTABLE_AUDIT=true` recusa | [MODELO-DE-AMEACAS.md](MODELO-DE-AMEACAS.md) |
| **Campo travado** (`locked`) | Ajuste de IA ou de escopo que veio do ambiente: a tela mostra e não troca. O ambiente vence a tela | [REFERENCIA.md](REFERENCIA.md#6-variáveis-de-ambiente) |
| **Adapter** | O código que embrulha um scanner atrás do protocolo `ScannerAdapter` (`health`, `start_scan`, `poll`, `fetch_results`, `normalize`). São 15 | [ESTENDER.md](ESTENDER.md) |
| **Scanner** | A ferramenta que o adapter conduz (nmap, ZAP, nuclei, trivy, semgrep...). Nove podem ser construídos por um scan comum, e mais cinco pelo pipeline OSINT | [REFERENCIA.md](REFERENCIA.md#7-scanners-e-suas-opções) |
| **Perfil** (`profile`) | O `profile` do scan: `web`, `network` ou `full` escolhem os scanners por tipo de alvo; `full` e `active` também ligam o active scan do ZAP; `exposure` roda o pipeline OSINT sobre o domínio do alvo. Outro valor é recusado com 422 | [REFERENCIA.md](REFERENCIA.md#8-perfis-de-scan) |
| **Active scan** | O ZAP mandando payloads de injeção de verdade, com o AJAX spider. Desligado no `web`, ligado no `full`. Mais lento e mais intrusivo | [REFERENCIA.md](REFERENCIA.md#8-perfis-de-scan) |
| **Opções de scanner** (`options`) | Os ajustes por scanner que o `POST /scans` aceita, de uma lista fechada com tipo e faixa. O resto é recusado com o nome do campo | [REFERENCIA.md](REFERENCIA.md#7-scanners-e-suas-opções) |
| **Scan autenticado** | Scan com `auth.headers` (cookie, authorization) e `openapi_url` opcional. O valor dos headers nunca chega ao banco: vai só no job e sai redigido na auditoria | [REFERENCIA.md](REFERENCIA.md#4-api-rest) |
| **Exposição** (exposure, OSINT) | O pipeline só de leitura sobre dado público: dorks no GitHub, gitleaks e trufflehog nos repos achados, dnstwist, shodan, subdomain takeover. Roda pelo `POST /exposure/scan`, pelo `cai exposure`, ou num scan com perfil `exposure` (sobre o domínio do alvo) | [REFERENCIA.md](REFERENCIA.md#3-a-cli-de-administração-cai) |
| **Achado** (finding) | Um problema que um scanner relatou, normalizado no modelo canônico `Finding`: severidade, título, local, evidência, ferramenta de origem | [ARQUITETURA.md](ARQUITETURA.md) |
| **`deduped_key`** | Um hash estável do achado. A deduplicação mantém o mais severo por chave, e a fila e a resolução de achados funcionam por chave, entre scans | [REFERENCIA.md](REFERENCIA.md#4-api-rest) |
| **Triagem** | A passada de IA sobre todo achado depois da deduplicação: severidade ajustada, justificativa, provável falso positivo, impacto no negócio, correção, categoria OWASP. Nunca sobrescreve a severidade do scanner; vai em `ai_triage.adjusted_severity` | [ARQUITETURA.md](ARQUITETURA.md) |
| **Scrubber** | `orchestrator/domain/scrubber.py`: tira dado pessoal e de cartão (CPF, CNPJ, número de cartão, CVV, e-mail e outros) dos achados antes de irem a um modelo externo | [MODELO-DE-AMEACAS.md](MODELO-DE-AMEACAS.md) |
| **Redação** | Diferente do scrubber: tira credencial (bearer token, cookie, `usuario:senha@` em URL) do log e do stream de log ao vivo antes de alguém ver | [MODELO-DE-AMEACAS.md](MODELO-DE-AMEACAS.md) |
| **Fallback para a nuvem** | Quando um modelo local falha, o gateway pode cair no `LLM_FALLBACK_MODEL` da nuvem. `ALLOW_CLOUD_FALLBACK=false` proíbe, e a triagem falha em vez disso | [REFERENCIA.md](REFERENCIA.md#6-variáveis-de-ambiente) |
| **Cobertura** | Se todo scanner que o scan pediu de fato rodou. Três estados: `completa`, `incompleta`, `desconhecida`. Só a completa permite ler zero achado como limpo | [REFERENCIA.md](REFERENCIA.md#4-api-rest) |
| **Cobertura incompleta** | Pelo menos um scanner não rodou. A tela, os relatórios, o bundle, a CLI (saída 3) e o MCP (`isError: true`) dizem isso. Scan em que nenhum rodou termina `failed` | [QUANDO-QUEBRA.md](QUANDO-QUEBRA.md) |
| **`scanners_ran`** / **`scanners_skipped`** | O que rodou de fato, e o que não rodou com o motivo (scanner para mensagem). É a fonte do estado da cobertura | [REFERENCIA.md](REFERENCIA.md#4-api-rest) |
| **`coverage_gaps`** | Campo do resultado bruto de um adapter para uma verificação parcial (linha ilegível, página que não carregou). O pipeline transforma em achado INFO, para a lacuna aparecer no relatório e no bundle | [ESTENDER.md](ESTENDER.md) |
| **`ScanIntegrityError`** | A exceção que o adapter levanta quando não pode garantir o resultado (saída ausente, relatório que não parseia, zero regras carregadas). O pipeline registra o scanner em `scanners_skipped` | [ESTENDER.md](ESTENDER.md) |
| **Contrato do silêncio** | A regra de que um scanner quebrado nunca pode parecer alvo limpo: devolver `[]` só se rodou e não achou, levantar `ScanIntegrityError` se não deu para verificar, preencher `coverage_gaps` se verificou em parte. Executada pelo `scripts/check_no_silence.py` no CI | [ESTENDER.md](ESTENDER.md) |
| **Contrato de códigos de saída** | `roqueshield scan start --wait` e `scan watch` saem com 0 (limpo), 1 (achado no limite do `--fail-on` ou acima), 2 (uso ou conexão), 3 (falhou ou cobertura incompleta). O 3 vence o 0 e o 1 | [REFERENCIA.md](REFERENCIA.md#códigos-de-saída) |
| **AI Fix Bundle** | O JSON (schema 1.0.0) com os achados deduplicados e priorizados, onde corrigir e como verificar, para outro agente corrigir o código. `GET /reports/{id}/ai-bundle`, `roqueshield report`, `cai bundle` | [AI-FIX-BUNDLE.md](AI-FIX-BUNDLE.md) |
| **Relatório executivo** | HTML para quem decide: nota de risco de A a F, aviso de cobertura e mapeamento de conformidade (OWASP, PCI DSS, LGPD) | [REFERENCIA.md](REFERENCIA.md#4-api-rest) |
| **Agente de investigação** | `POST /investigate/{finding_id}`: um loop ReAct em que o modelo planeja comandos contra um achado, vê a saída e segue. Com `AGENT_ENABLED=false`, volta ao parecer de um prompt só | [INTEGRACOES.md](INTEGRACOES.md) |
| **Coleira** (leash) | As checagens de `orchestrator/ai/agentic/executor.py` por que todo comando do agente passa antes de rodar: allowlist de binários por fase (recon, exploit), escopo, sem shell nem metacaractere, `dry_run`, timeout. Escrita no código, não no prompt | [MODELO-DE-AMEACAS.md](MODELO-DE-AMEACAS.md) |
| **`dry_run`** | Default `true` na investigação: o agente planeja e mostra os comandos, e nada roda | [REFERENCIA.md](REFERENCIA.md#4-api-rest) |
| **`AGENT_LIVE_EXECUTION`** | Desligado por padrão. Só com ele ligado, e só para quem tem `config:manage`, o `dry_run=false` roda os comandos planejados | [REFERENCIA.md](REFERENCIA.md#6-variáveis-de-ambiente) |
| **Sidecar Kali** (`cai-kali-toolbox`) | O container opcional do `docker/compose.scanners.yml` onde os comandos do agente rodam isolados. Com `AGENT_EXECUTOR=auto`, é usado quando está de pé; a imagem standalone não sobe ele, e os comandos rodam no próprio processo sob a mesma coleira | [ARQUITETURA.md](ARQUITETURA.md) |
| **MCP** | Model Context Protocol: como um agente de IA (Claude Code, Claude Desktop, Cursor) chama o RoqueShield. Por stdio (`roqueshield mcp`) ou HTTP (`POST /mcp`), com ferramentas de leitura e, opt-in, o `start_scan` | [REFERENCIA.md](REFERENCIA.md#5-servidor-mcp) |
| **Ações do MCP** | As ferramentas que agem (hoje, o `start_scan`). Desligadas por padrão: `ROQUESHIELD_MCP_ACTIONS=1` no stdio, `MCP_ALLOW_ACTIONS=true` no HTTP | [REFERENCIA.md](REFERENCIA.md#5-servidor-mcp) |
| **Rate limit** | Teto de `RATE_LIMIT_PER_MINUTE` chamadas por principal em `POST /scans`, `POST /exposure/scan` e `POST /investigate/{id}`. Acima disso, 429 | [REFERENCIA.md](REFERENCIA.md#4-api-rest) |

## Perguntas frequentes

### Zero achado: o alvo está limpo?

Só se a cobertura estiver completa (`coverage_complete: true`). Com cobertura incompleta ou desconhecida, zero achado quer dizer que algum vetor não foi verificado. A CLI sai com 3 e o MCP responde com `isError: true` nesse caso. Veja [QUANDO-QUEBRA.md](QUANDO-QUEBRA.md).

### Por que aparece `cai` em todo lugar?

É o nome interno do motor, de antes de o produto se chamar RoqueShield. O pacote, os containers da stack de desenvolvimento e a CLI de administração ainda usam. A CLI para quem usa é a `roqueshield`.

### O agente roda comando contra o meu alvo sozinho?

Não por padrão. A investigação roda com `dry_run=true` e só planeja. Rodar de verdade exige `AGENT_LIVE_EXECUTION=true` no servidor e um admin pedindo `dry_run=false`, e mesmo assim todo comando passa pela coleira e vai para a trilha de auditoria.
