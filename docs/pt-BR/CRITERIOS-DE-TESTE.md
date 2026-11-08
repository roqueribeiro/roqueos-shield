# Critérios de teste

*Tradução de [TESTING.md](../TESTING.md), a versão principal, em inglês. Se as duas divergirem, vale a em inglês.*

> A lista única do que o RoqueShield tem que provar antes de um relatório sair para alguém. Para quem muda um scanner, o pipeline ou a triagem, e para quem revisa essa mudança. Cada critério diz o que provar, como se prova (o teste, o gate ou o passo manual que executa) e o que reprova. Como montar o ambiente que roda isto está em [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md); como adicionar um scanner com os testes dele, em [ESTENDER.md](ESTENDER.md).

## Sumário

1. [Por que esta lista existe](#1-por-que-esta-lista-existe)
2. [Pré-condições de um engagement](#2-pré-condições-de-um-engagement)
3. [SAST: Semgrep](#3-sast-semgrep)
4. [Segredos: Gitleaks e Trufflehog](#4-segredos-gitleaks-e-trufflehog)
5. [Dependências, CVE e IaC: Trivy e Checkov](#5-dependências-cve-e-iac-trivy-e-checkov)
6. [DAST: OWASP ZAP e Nuclei](#6-dast-owasp-zap-e-nuclei)
7. [Rede: Nmap e Greenbone](#7-rede-nmap-e-greenbone)
8. [OSINT e exposição externa](#8-osint-e-exposição-externa)
9. [Triagem de IA](#9-triagem-de-ia)
10. [A coleira do agente de investigação](#10-a-coleira-do-agente-de-investigação)
11. [Os gates que seguram tudo](#11-os-gates-que-seguram-tudo)
12. [O que rodar, por tipo de alvo](#12-o-que-rodar-por-tipo-de-alvo)
13. [Como rodar a bateria](#13-como-rodar-a-bateria)
14. [Quando algo não funciona](#14-quando-algo-não-funciona)

## 1. Por que esta lista existe

Uma frase governa o repositório inteiro:

> **Zero achados aqui significa *limpo*, ou significa *não rodou*? Se não houver como distinguir, falta um sinal.**

Um scanner quebrado e um alvo seguro produzem a mesma saída: zero achados. Num relatório que vai para a auditoria de um banco, essa é a única diferença que importa. Os critérios abaixo existem para que os mesmos testes rodem sempre e as duas coisas nunca se confundam.

Critério sem mecanismo que o execute é decoração, então toda linha aponta para o teste, o gate ou o passo manual que a verifica. Os nomes de teste são reais: cada um existe em `tests/`.

## 2. Pré-condições de um engagement

Isto não é teste de software. É o contrato de uso, vale para todo scan contra ativo real, e o CI não substitui o julgamento humano aqui.

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| O alvo está autorizado por escrito | `authorization_ref` preenchido no `POST /scans` quando `REQUIRE_AUTH_REF=true` | 403 sem o ticket ou a aprovação formal |
| O escopo está fechado | `LAB_ONLY=true` (o padrão) com `TARGET_ALLOWLIST` contendo o escopo escrito; alvo fora dela é recusado | alvo fora da allowlist roda |
| Janela acordada | combinada com o dono do ativo antes do scan ativo | scan ativo sem janela |
| Dado pessoal não chega a LLM externo | `orchestrator/domain/scrubber.py` redige PII e PCI antes de qualquer saída para modelo externo | evidência com CPF ou número de cartão chega crua no provedor |

Alvo de laboratório (Juice Shop, DVWA, WebGoat) e ativo do próprio engagement. Nunca alvo de terceiro sem autorização, nunca alvo externo "só para testar".

## 3. SAST: Semgrep

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| O SAST roda com egress fechado | o ruleset `semgrep-rules` vai embarcado na imagem (`/opt/semgrep-rules`), pinado por commit (`SEMGREP_RULES_COMMIT`) | `--config auto` com `--metrics off`: sai 0, zero regras, zero achados |
| Acha injeção de comando | `test_efetividade_e2e.py` exige regra com `subprocess` no repositório sintético | `subprocess` ausente das regras disparadas |
| Acha SQL por concatenação | mesmo teste, termo `sql` | ausente |
| Acha desserialização insegura | mesmo teste, termo `deserialization` (pickle) | ausente |
| Acha hash fraco | mesmo teste, termo `md5` | ausente |
| Recusa config que não resolve | `test_semgrep_recusa_auto_em_vez_de_falhar_calado`: `start_scan` com `config=auto` levanta `ValueError` | `start_scan` aceita `config=auto` e segue calado |

Piso: pelo menos 5 achados do Semgrep no repositório sintético. Menos que isso é SAST raso, e reprova.

## 4. Segredos: Gitleaks e Trufflehog

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| Report ausente ou ilegível não vira "repositório limpo" | `test_gitleaks_sem_report_nao_e_repo_limpo`, `test_gitleaks_report_corrompido_reprova`; o `read_jsonl` de `adapters/base.py` reprova quando toda linha é ilegível e preserva as boas, declarando a lacuna, quando só parte é | `except json.JSONDecodeError: continue` virando `{}` |
| Credencial rotacionada não colapsa num achado só | `dedup_discriminator` no achado, que entra no `deduped_key` | dois segredos distintos viram um |
| Clone raso é declarado | `test_gitleaks_clona_o_historico_inteiro_por_padrao`, `test_gitleaks_clone_raso_declara_a_lacuna` | `clone_depth` corta o histórico e o relatório não diz |
| Segredo não verificado não some calado | `--only-verified` vem desligado; achado não verificado sai MEDIUM e TENTATIVE (`test_trufflehog_nao_descarta_segredo_nao_verificado_por_padrao`); com `only_verified: true` o descarte é declarado (`test_trufflehog_com_only_verified_declara_o_descarte`) | segredo não verificado some do relatório |

## 5. Dependências, CVE e IaC: Trivy e Checkov

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| IaC com bucket público é pego | `test_efetividade_e2e.py` exige pelo menos 3 achados do Checkov e ao menos uma regra `CKV_*` | o Checkov não produz nenhum `CKV_*` |
| O Checkov recebe diretório, nunca URL | o pipeline passa o caminho do repositório clonado (`test_checkov_adapter.py`) | o Checkov recebe `-d <url>`, loga "Directory does not exist", sai 0 com saída vazia |
| Scanner ausente é declarado, não some | sem trivy na máquina, `scanners_skipped` contém `trivy` e `coverage_is_complete` é falso (segunda metade do teste de efetividade) | trivy ausente vira "zero CVEs" |
| Artefato que o Trivy não identificou não é imagem limpa | `test_trivy_sem_secao_de_resultado_nao_e_imagem_limpa`: sem seção `Results` vira lacuna declarada | imagem scratch ou distroless relatada como "sem CVE" |
| Security group `0.0.0.0/0`, disco sem cifra, debug ligado | achados reais no repositório sintético | qualquer um ausente |

## 6. DAST: OWASP ZAP e Nuclei

O alvo web típico é uma SPA, e por isso estes critérios são os mais sensíveis.

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| SPA (Angular, React, Vue) é percorrida de verdade | `options.zap.ajax=true` sobe o AJAX spider; os perfis `full` e `active` e o `--active-zap` da CLI ligam active scan e AJAX juntos | só o spider tradicional: zero URL rastreada numa SPA |
| Active scan testa injeção, não só header | perfil `full` ou `active` liga `zap.active=true` | perfil `web` (passivo, o padrão) vendido como se testasse injeção |
| Spider que não rastreou nada não é alvo limpo | `test_zap_sem_url_rastreada_nao_e_app_segura`, `test_zap_conta_urls_antes_de_fechar` | fila passiva vazia lida como "terminou" |
| AJAX spider indisponível é lacuna, não silêncio | `test_zap_ajax.py::test_ajax_indisponivel_vira_lacuna_declarada_e_o_scan_segue` | add-on `spiderAjax` ausente fecha o scan "limpo" |
| Alertas paginados até o fim, redirecionamento declarado | `test_zap_pagina_todos_os_alertas`, `test_zap_alerta_fora_do_prefixo_vira_lacuna`, `test_zap_saude.py::test_alertas_paginados_ate_o_fim_e_redirecionamento_vira_lacuna_declarada` | uma página de 500 lida como total; alertas do destino do redirecionamento somem |
| Ferramenta de rede com egress fechado | o nuclei roda com `-duc -ni`; o build da imagem falha abaixo de 2000 templates (`NUCLEI_TEMPLATES_MIN`) | o nuclei pendura até o timeout em rede restrita, ou imagem sem templates |

**Efetividade no laboratório** (precisa de Docker e do perfil `lab`): `make smoke` roda `--active-zap` contra o Juice Shop. O script não confere o resultado sozinho: imprime onde está o relatório. A conferência é sua: abra `reports/scan-*.html` e procure achados reais de injeção (SQLi, XSS). Zero achados aqui é reprovação, não aplicação segura.

## 7. Rede: Nmap e Greenbone

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| `poll` lê o returncode, não só `task.done()` | adapter de subprocesso devolve `(rc, path)` e o `poll` lê `rc`; o `check_no_silence.py` reprova `poll` que não lê | `task.done()` lido como sucesso |
| Serviço inseguro exposto é HIGH | `_severity_for_service` no `nmap_adapter.py`: telnet, ftp, rsh, rexec, rlogin, tftp são HIGH; smb, portas de banco e redis são MEDIUM | serviço inseguro sai como INFO |
| O Greenbone lê o status do GMP, não só XML que parseia | `test_greenbone_confere_o_status_do_gmp` | resposta de erro do GMP lida como relatório vazio |

**Limite conhecido:** nada confere se o feed sync do Greenbone terminou. O `health()` só autentica pelo GMP. Um scan disparado durante o primeiro sync (30 min a 3 h) roda contra uma base de NVT incompleta e não diz.

## 8. OSINT e exposição externa

Leitura sobre dado público.

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| Rate limit não abandona dork calado | `test_github_rate_limit_declara_dorks_nao_consultadas`, `test_github_rate_limit_na_primeira_dork_reprova` | 3 de 10 dorks rodadas, relatadas como 10 |
| Shodan e Censys não fabricam vazio em erro | `test_shodan_falha_de_busca_nao_vira_zero_exposicoes`, `test_censys_erro_sem_resultado_reprova` e os testes de página parcial | cota estourada lida como "nada exposto" |
| Subdomain takeover confere cada etapa | `test_subtake_etapa_que_falha_reprova`, `test_subtake_sem_saida_nao_e_dominio_seguro`, `test_subtake_usa_duc_e_ni_no_nuclei` | etapa que falha apaga as seguintes |
| `health()` faz round-trip | construir cliente de SDK não conta como health | chave inválida passa no health e a busca falha calada |

Os adapters do Censys e do kube-bench existem e têm teste, mas nenhum caminho de produção os constrói hoje: nem a fábrica do scan (`_build_adapters`) nem o pipeline de exposição (`orchestrator/jobs/exposure.py`).

## 9. Triagem de IA

Sobre evidência já higienizada.

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| PII e PCI não saem para LLM externo | o `scrubber.py` roda antes de qualquer payload sair; `test_scrubber.py` | CPF, número de cartão, JWT ou Bearer na mensagem ao provedor |
| A severidade do scanner é preservada | a triagem escreve em `ai_triage.adjusted_severity`, nunca em `Finding.severity` | severidade original sobrescrita |
| Resposta malformada do LLM não derruba o scan | `triage_batch` loga `ai.triage_parse_failed` e segue | exceção de parse quebra o pipeline |
| Soberania de dado é interruptor, não esperança | `ALLOW_CLOUD_FALLBACK=false` com modelo local: o fallback para a nuvem é bloqueado (`test_gateway_sovereignty.py::test_cloud_fallback_blocked_when_disabled`) | fallback calado para a nuvem com dado sensível |

## 10. A coleira do agente de investigação

A investigação profunda roda com `dry_run=true` por padrão, e a execução real ainda exige `AGENT_LIVE_EXECUTION=true`. A coleira é código em `orchestrator/ai/agentic/executor.py`, não uma frase no prompt.

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| Alvo fora da allowlist é recusado | `test_agent_executor.py`: comando contra host fora do escopo volta recusado | o comando roda fora do escopo |
| Brute force é proibido em qualquer fase | o executor nega `hydra`, `medusa`, `patator`, `ncrack` | algum binário de brute force roda |
| Sem shell, sem metacaractere para escapar | `argv` como lista para `create_subprocess_exec`; argumento com metacaractere de shell é recusado (`test_coleira_argv.py`) | comando montado como string de shell |
| Flag de escrita em disco é negada | o executor recusa flags que gravam, leem arquivo local ou dão shell (`--os-shell`, `--sql-shell` e outras) | scan "só leitura" grava no alvo |
| `dry_run=true` planeja, não executa | a decisão volta com `executed=false` e o motivo `dry_run: comando planejado, não executado` | o comando roda com dry_run ligado |
| Toda decisão, inclusive recusa, vai para o audit | `ExecDecision.to_audit()` | recusa sem registro |

Quando o executor muda, a prova exigida no fechamento é um teste mostrando que a coleira recusa alvo fora da allowlist.

## 11. Os gates que seguram tudo

| Gate | O que faz | Teste de mutação |
| --- | --- | --- |
| **silencio** (`scripts/check_no_silence.py`) | reprova `except` vazio no ciclo de vida do scan, `poll` que decide por `task.done()`, payload de sucesso fabricado e persistência que não grava a cobertura | quatro plantios, todos `exit 1`; as burlas do próprio gate são testes em `test_gate_do_silencio.py` |
| **efetividade** (`tests/integration/test_efetividade_e2e.py`) | monta um repositório com defeito conhecido e exige achado real de cada camada | com `--config auto`, o SAST não roda e o gate reprova |
| **docs** (`scripts/check_docs_fresh.py`) | todo scanner construível aparece na doc, a contagem de adapters bate, todo campo de `Settings` está no `.env.example`, nada é chamado de "stub" se já roda, os pares de docs e os links resolvem | scanner sem doc, campo de `Settings` fora do `.env.example`, doc chamando o agente de stub |

O gate é o piso, não o teto. Check que nunca reprovou não é check: antes de declarar um gate pronto, quebre de propósito e confirme que ele reprova.

## 12. O que rodar, por tipo de alvo

| Tipo de alvo | Scanners | Critério mínimo |
| --- | --- | --- |
| URL, app web SPA | zap (active e ajax) e nuclei: perfil `full` | achados de injeção reais; URLs rastreadas > 0 |
| URL, app web clássico | zap (active) e nuclei | achados; AJAX não obrigatório |
| Host ou IP | nmap (e greenbone quando pedido) | portas e serviços; severidade por heurística |
| Domínio | perfil `full`: nmap, zap e nuclei | o mesmo de web mais rede |
| Imagem de container | trivy | CVEs por camada; artefato que o Trivy não identificou é lacuna declarada |
| Repositório | semgrep, gitleaks, trufflehog, trivy, checkov | achado de cada camada presente no código |
| Exposição externa | github, gitleaks e trufflehog nos repositórios achados, dnstwist, shodan, subdomain takeover | leitura de dado público; nada ativo |

Sem perfil nem lista de scanners, cada tipo recebe o padrão (`_DEFAULT_SCANNERS` em `orchestrator/jobs/pipelines.py`): URL e domínio recebem `zap`, host e porta recebem `nmap`. Em todos os casos, scanner incompatível com o tipo de alvo é filtrado antes do scan, e scanner que não pôde rodar aparece em `scanners_skipped`, nunca como zero achados.

## 13. Como rodar a bateria

Com o ambiente de desenvolvimento de [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md#7-gates-locais):

```bash
.venv/bin/pytest                                  # unidade e integração, nada que precise de Docker
python scripts/check_no_silence.py                # o gate do silêncio
python scripts/check_docs_fresh.py                # o gate da doc
.venv/bin/pytest tests/integration                # só a pasta de integração
.venv/bin/pytest tests/integration/test_efetividade_e2e.py -v   # precisa de semgrep e checkov no PATH
make smoke                                        # o laboratório: scan ativo no Juice Shop (Docker)
```

**O que você deve ver** do `pytest` numa máquina sem checkov (medido em 2026-11-08):

```
610 passed, 8 skipped
```

Os pulados são os testes que precisam de um binário que não está instalado. O teste principal de efetividade pula sem semgrep e checkov, com o motivo `precisa de semgrep e checkov instalados`. Pulado não é aprovado: o job `efetividade` do CI instala os dois para ele rodar.

Não existe marcador `integration`: `pytest -m integration` não seleciona nada (56 deselected). Os testes de integração rodam com `pytest` puro, a partir de `tests/integration`. O `make test` não funciona como está escrito; [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md#5-dia-a-dia) explica por quê.

A evidência de qualquer entrega é a saída crua destes comandos, colada sem resumo. Scan de laboratório sempre; nunca apontar teste para ativo real nem para qualquer alvo externo.

## 14. Quando algo não funciona

- **O teste de efetividade pula**: semgrep ou checkov não está no `PATH`. O CI instala o checkov num venv próprio (`checkov==3.3.15`) e liga no `PATH`, porque no ambiente do app o resolvedor do pip não terminava.
- **A camada SAST não acha nada**: olhe a config do Semgrep. `config=auto` é recusada de propósito; config que não resolve dá zero regras.
- **`make smoke` fecha com zero achados no Juice Shop**: isso é reprovação. Confira se o ZAP rodou ativo com AJAX (`--active-zap`) e se `scanners_skipped` está vazio no relatório.
- **Um gate reprova código que você não mexeu**: leia a linha que ele imprimiu. Ela diz o arquivo, a linha e a regra. O conserto é no código ou no gate (com o caso novo virando teste), nunca um comentário que silencia sem motivo. O escape `# silencio-ok: <motivo>` existe para o vazio que é mesmo o resultado certo.
- **Mais sobre scan que quebra**: [QUANDO-QUEBRA.md](QUANDO-QUEBRA.md).
