# Critérios de teste do RoqueShield

Este documento é a lista única do que a ferramenta tem que provar antes de um
relatório sair para alguém. Ele existe para uma frase só, a mesma que governa o
repositório inteiro:

> **Zero achados aqui significa *limpo*, ou significa *não rodou*? Se não houver como
> distinguir, falta um sinal.**

Um scanner quebrado e um alvo seguro produzem a mesma saída: zero achados. Num
relatório que vai para a auditoria de um banco, essa é a única diferença que importa.
Os critérios abaixo são escritos para que a gente sempre siga os mesmos testes e nunca
confunda as duas coisas.

Cada critério tem três colunas de verdade: **o que provar**, **como provar** (o comando
ou o teste que executa), e **o que reprova**. Critério sem mecanismo que o execute é
decoração, então todo item aponta para o teste, o gate ou o passo manual que o verifica.

---

## 0. Pré-condições de um engagement (antes de qualquer scan ativo)

Estes não são testes de software, são o contrato de uso. Valem para todo scan contra
ativo real, e o CI não substitui o julgamento humano aqui.

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| O alvo está autorizado por escrito | `authorization_ref` preenchido no `POST /scans` quando `REQUIRE_AUTH_REF=true` | 403 sem o ticket/aprovação formal |
| O escopo está fechado | `LAB_ONLY=true` + `TARGET_ALLOWLIST` com o escopo escrito; alvo fora da lista é recusado | alvo fora da allowlist roda |
| Janela acordada | combinada com o dono do ativo antes do ativo | scan ativo sem janela |
| Dados pessoais não vazam para LLM externo | `scrubber.py` redige PII/PCI antes de qualquer saída para modelo externo | evidência com CPF/PAN chega crua no provider |

Alvo de laboratório (Juice Shop, DVWA, WebGoat) e ativo próprio do engagement. Nunca
um alvo de terceiro sem autorização, nunca um alvo externo "só para testar".

---

## 1. Camada SAST (código-fonte) — Semgrep

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| O SAST roda mesmo com egress fechado | regras `semgrep-rules` embarcadas na imagem (`/opt/semgrep-rules`), pinadas por commit | `--config auto` com `--metrics off`: sai código 0, zero regras, zero achados |
| Acha injeção de comando | `test_efetividade_e2e.py` exige regra com `subprocess` no repo sintético | `subprocess` não aparece nas regras disparadas |
| Acha SQL por concatenação | idem, termo `sql` | ausente |
| Acha desserialização insegura | idem, termo `deserialization` (pickle) | ausente |
| Acha hash fraco | idem, termo `md5` | ausente |
| Rejeita config que não resolve | `test_semgrep_recusa_auto_em_vez_de_falhar_calado` | `start_scan` aceita `config=auto` e segue calado |

Piso: pelo menos 5 achados do semgrep no repo sintético. Menos que isso é SAST raso, e
reprova.

---

## 2. Camada de segredos — Gitleaks + Trufflehog

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| Report ausente ou ilegível não vira "repo limpo" | `read_jsonl` em `adapters/base.py`: linha ilegível reprova, parte ilegível preserva e declara a lacuna | `except json.JSONDecodeError: continue` virando `{}` |
| Credencial rotacionada não colapsa em um achado só | dedup por `deduped_key` com discriminador | dois segredos distintos viram um |
| Verificação de segredo (trufflehog `--only-verified`) é declarada | achado marca se o segredo foi verificado contra o provedor | "verificado" sem round-trip |

---

## 3. Camada de dependências, CVE e IaC — Trivy + Checkov

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| IaC com bucket público é pego | `test_efetividade_e2e.py` exige ao menos um `CKV_*` e termos do `main.tf` vulnerável | checkov não produz nenhum `CKV_*` |
| Checkov recebe diretório, nunca URL | o pipeline passa path de repo clonado, não a URL | checkov recebe `-d <url>`, loga "Directory does not exist", sai 0 e vazio |
| Scanner ausente é declarado, não some | sem trivy na máquina: `scanners_skipped` contém `trivy` e `coverage_is_complete=false` | trivy ausente vira "zero CVEs" |
| Security group `0.0.0.0/0`, disco sem cifra, debug ligado | achados reais das três camadas no repo sintético | qualquer um ausente |

---

## 4. Camada DAST (aplicação rodando) — OWASP ZAP + Nuclei

Esta é a camada da vergonha de hoje, e a que ganhou o AJAX spider. Os critérios aqui
são os mais sensíveis porque o alvo típico é uma SPA.

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| SPA (Juice Shop, Angular/React/Vue) é percorrida de verdade | `options['ajax']=True` sobe o AJAX spider antes do active scan; `profile` ativo e `--active-zap` ligam os dois juntos | spider tradicional só: zero URL rastreada numa SPA |
| Active scan testa injeção, não só headers | `profile` `full`/`active` → `zap.active=True` | profile `web` (passivo) vendido como se testasse injeção |
| Spider que não rastreou nada não vira alvo limpo | `fetch_results` conta URLs; zero URL → `ScanIntegrityError` | fila passiva vazia lida como "terminou" |
| AJAX spider indisponível vira lacuna, não silêncio | `test_zap_ajax.py::test_ajax_indisponivel_vira_lacuna_declarada_e_o_scan_segue` | add-on `spiderAjax` ausente fecha scan "limpo" |
| Alertas paginados até o fim | `test_alertas_paginados_ate_o_fim...`: compara total da sessão com o filtrado | uma página de 500 lida como total |
| Redirecionamento para outro host é declarado | gap quando o total da sessão > alertas sob o prefixo | alertas do destino somem do relatório |
| Ferramenta de rede com egress fechado | nuclei com `-duc -ni`; imagem falha abaixo de 2000 templates | nuclei pendura até timeout em rede restrita, ou imagem sem templates |

**Prova de efetividade no lab** (precisa de Docker e do profile `lab`): `make smoke` roda
`--active-zap` contra o Juice Shop e tem que produzir achados de injeção reais (SQLi,
XSS). Zero achados aqui é reprovação, não "aplicação segura". Este é o critério que
teria pego a falha de hoje.

---

## 5. Camada de rede — Nmap + Greenbone/OpenVAS

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| `poll` lê o returncode, não só `task.done()` | adapter de subprocess devolve `(rc, path)` e o poll lê `rc` | `task.done()` lido como sucesso |
| Serviço inseguro exposto é HIGH | heurística de severidade documentada no adapter (telnet/ftp/smb → high) | serviço inseguro vira info |
| Greenbone que não terminou o feed sync não reporta cobertura completa | health com round-trip; feed incompleto declara lacuna | scan roda contra base de CVE desatualizada em silêncio |

---

## 6. Camada OSINT / Exposição externa (read-only sobre dado público)

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| Rate limit não abandona dorks em silêncio | `github_exposure` não dá `break` deixando dorks para trás sem declarar | 3 de 10 dorks rodadas reportadas como 10 |
| Shodan/Censys não fabricam vazio em erro | exceção vira lacuna, nunca `{"matches": [], "total": 0}` | cota estourada lida como "nada exposto" |
| `health()` faz round-trip | construir cliente de SDK não conta como health | chave inválida passa no health e a busca falha calada |

---

## 7. Triagem AI (sobre evidência já higienizada)

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| PII/PCI não sai para LLM externo | `scrubber.py` roda antes de qualquer payload sair; `test_scrubber.py` | CPF/PAN/JWT/Bearer na mensagem ao provider |
| Severity do scanner é preservada | triagem escreve em `ai_triage.adjusted_severity`, nunca em `Finding.severity` | severity original sobrescrita |
| Formato errado do LLM não derruba o scan | `triage_batch` loga `ai.triage_parse_failed` e segue | exceção de parse quebra o pipeline |
| Soberania de dado é interruptor, não esperança | `ALLOW_CLOUD_FALLBACK=false` + modelo local: modelo que falha reprova o scan em vez de mandar para a nuvem | fallback silencioso para cloud com dado sensível |

---

## 8. A coleira do agente de investigação

A investigação profunda roda sob HITL e `dry_run=true` por padrão. A coleira é código
em `agentic/executor.py`, não uma frase no prompt.

| O que provar | Como provar | O que reprova |
| --- | --- | --- |
| Alvo fora da allowlist é recusado | teste do executor: comando contra host fora do escopo volta recusado | comando roda fora do escopo |
| Brute force é proibido em qualquer fase | allowlist do executor nega `hydra`/`medusa`/`patator`/`ncrack`; prompt do agente nunca propõe | qualquer binário de brute force executa |
| Sem shell, sem metacaractere para escapar | `argv` como lista para `create_subprocess_exec`, nunca shell | comando montado como string de shell |
| Flag de escrita em disco é negada | o executor recusa flags que gravam | scan "read-only" grava no alvo |
| `dry_run=true` planeja, não executa | decisão `PLANEJADO` no audit, `executed=false` | comando roda com dry_run ligado |
| Toda decisão, inclusive recusa, vai para o audit | `ExecDecision.to_audit()` append-only | recusa sem registro |

Quando o executor muda, a prova exigida no fechamento é: a trava recusa alvo fora da
allowlist, demonstrada por teste.

---

## 9. Os dois gates que seguram tudo (CI)

| Gate | O que faz | Teste de mutação |
| --- | --- | --- |
| **silêncio** (`scripts/check_no_silence.py`) | reprova `except` vazio no ciclo de vida do scan, `poll` que decide por `task.done()`, payload de sucesso fabricado | quatro plantios, todos `exit 1`; árvore limpa `exit 0` |
| **efetividade** (`tests/integration/test_efetividade_e2e.py`) | monta repo com defeito conhecido e exige achado real de cada camada | com `--config auto` o SAST não roda e o gate reprova |
| **docs em dia** (`scripts/check_docs_fresh.py`) | todo adapter construível aparece na doc, todo `Settings` no `.env.example`, nada chamado de "stub" que já é código | adapter novo sem doc, Settings sem `.env.example`, doc regredindo para "stub" |

O gate é o piso, não o teto. Check que nunca reprovou não é check: antes de declarar
um gate pronto, quebre de propósito e confirme que ele reprova.

---

## 10. Matriz de casos de uso (o que rodar, por tipo de alvo)

| Tipo de alvo | Scanners | Critério mínimo |
| --- | --- | --- |
| URL / app web SPA | zap (active+ajax) + nuclei | achados de injeção reais; URLs rastreadas > 0 |
| URL / app web clássico | zap (active) + nuclei | achados; sem necessidade obrigatória de ajax |
| Host / IP | nmap (+ greenbone) | portas e serviços; severidade por heurística |
| Domínio | zap + nuclei + nmap | idem web + rede |
| Imagem de container | trivy | CVEs por camada; imagem sem CVE conhecida declara a versão da base de dados |
| Repositório | semgrep + gitleaks + trufflehog + trivy + checkov | achado de cada camada presente no código |
| Exposição externa | dnstwist + subdomain-takeover + shodan + github | leitura sobre dado público; nada ativo |

Em todos: scanner incompatível com o tipo de alvo aparece em `scanners_skipped`, nunca
vira "zero achados".

---

## 11. Como rodar a bateria

```bash
make test                               # pytest: unit + o que não precisa de stack
uv run python scripts/check_no_silence.py   # gate do silêncio
uv run python scripts/check_docs_fresh.py   # gate de docs em dia
make smoke                              # E2E no lab: Juice Shop ativo, acha de verdade
pytest tests/integration -m integration # integração contra a stack docker (opt-in)
```

A evidência de qualquer entrega é a saída crua destes comandos colada no chat, sem
resumo. Scan de laboratório sempre; nunca apontar teste para ativo real do banco ou
para qualquer alvo externo.
