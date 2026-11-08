# Quando quebra

*Tradução de [WHEN-IT-BREAKS.md](../WHEN-IT-BREAKS.md), a versão principal, em inglês. Se as duas divergirem, vale a em inglês.*

> **Para quem:** quem está olhando para um erro, para um scan que voltou estranho, ou para um container que não responde.
> **O que tem aqui:** sintoma, causa e o que fazer, na ordem em que você encontra: instalar, entrar, disparar um scan, ler o resultado, o próprio container, produção, e o que fazer quando um scan tocou o que não devia.
> **Onde ir para o resto:** como as coisas deveriam funcionar está em [OPERACAO.md](OPERACAO.md); a primeira instalação, em [COMECAR.md](COMECAR.md).

A regra de fundo desta ferramenta: **zero achado só é "limpo" quando todo scanner rodou.** Um scanner quebrado produz a mesma saída de um alvo seguro, então o RoqueShield marca o scanner que não rodou como pulado e a cobertura como incompleta, em vez de devolver silêncio. Quando aparecer **Cobertura incompleta**, acredite.

**Sobre o idioma:** o instalador imprime em português quando o seu `LANG` é português. O log do container, a CLI `roqueshield` e as mensagens de erro da API saem em português e vão citadas abaixo exatamente como aparecem.

## Sumário

1. [Instalação](#1-instalação)
2. [Primeiro uso e login](#2-primeiro-uso-e-login)
3. [Disparar um scan](#3-disparar-um-scan)
4. [Ler o resultado](#4-ler-o-resultado)
5. [IA](#5-ia)
6. [O próprio container](#6-o-próprio-container)
7. [Compose de produção](#7-compose-de-produção)
8. [Resposta a incidente](#8-resposta-a-incidente)
9. [Onde olhar](#9-onde-olhar)

## 1. Instalação

Todo erro do instalador começa com `Não deu:` e sai com código 1.

| O que aparece | Causa | O que fazer |
| --- | --- | --- |
| `o Docker não está instalado.` | não há comando `docker` no `PATH` | instale o Docker Desktop (Mac, Windows) ou o Docker Engine (Linux) e rode o comando de novo |
| `o Docker está instalado mas não respondeu.` | o daemon não está rodando, ou ainda está subindo | abra o Docker Desktop e espere terminar de iniciar; no Linux, `sudo systemctl start docker` |
| `seu usuário não tem permissão no Docker.` | Linux: seu usuário não está no grupo `docker` | `sudo usermod -aG docker $USER`, saia e entre de novo na sessão |
| `! o Docker tem cerca de N GB de memória; o RoqueShield pede 6 GB.` | o Docker informa menos de 5,5 GiB | é aviso, não erro. Aumente no Docker Desktop (Settings > Resources > Memory); com menos, um scanner pode ser morto no meio do scan |
| `não consegui baixar roqueribeiro1988/roqueos-shield:...` | sem conexão com o Docker Hub, ou uma versão que não existe | confira a conexão e o `ROQUESHIELD_VERSAO`; se a imagem já está na máquina, o instalador usa e avisa |
| `o container não subiu. Se a porta 8080 está em uso, escolha outra:` | outro programa ocupa a porta, quase sempre | `curl -fsSL .../install.sh \| ROQUESHIELD_PORTA=8081 sh` |
| `o container não ficou saudável. As últimas linhas do log estão acima.` | o container parou ou o healthcheck falhou | leia essas linhas; as causas mais comuns estão na [seção 6](#6-o-próprio-container) |
| `passaram 3 minutos e ele não ficou pronto.` | um primeiro boot lento (migrations, ZAP) ou um processo em laço de reinício | `docker logs roqueshield`; rode o instalador de novo, ele só espera outra vez |
| `opção desconhecida: --foo (use --update ou --no-browser)` | uma opção que o script não conhece | o script aceita só `--update` e `--no-browser` (ou `--atualizar`, `--nao-abrir`) |
| `a porta tem que ser um número (veio 'abc').` | `ROQUESHIELD_PORTA` não é um número entre 1 e 65535 | corrija a variável |
| `! o container 'roqueshield' é de ... (este script instala ...).` | o container é de outra versão | é aviso: ele liga o antigo. Para atualizar, acrescente `--update` |
| O navegador não abriu, ou abriu em branco | sem tela (um servidor, WSL sem `wslview`), ou o navegador não leu a página temporária | abra `http://localhost:8080` você mesmo; o código está em `docker exec roqueshield cat /data/secrets/SETUP_CODE` |

## 2. Primeiro uso e login

| O que aparece | Causa | O que fazer |
| --- | --- | --- |
| `código de primeiro uso ausente ou errado`, HTTP 403 | o código não foi preenchido, ou foi digitado errado | `docker exec roqueshield cat /data/secrets/SETUP_CODE` e cole inteiro |
| `muitas tentativas; espere antes de tentar de novo`, HTTP 429 | códigos errados seguidos da mesma origem | espere o tempo do `Retry-After` e use o código certo |
| `o primeiro uso já foi feito`, HTTP 410 | já existe um admin | entre pelo login; se ninguém lembra a senha, veja a próxima linha |
| Esqueci a senha do admin | | `docker exec -it roqueshield roqueshield reset-password <email>` (a CLI de dentro do container usa o `APP_TOKEN`) |
| `a senha precisa de pelo menos 10 caracteres` | | uma senha maior; ela também não pode começar nem terminar com espaço |
| O login espera 30 s, depois mais | 5 senhas erradas seguidas para o mesmo e-mail do mesmo IP; a espera dobra até 15 min | espere, ou troque a senha. Reiniciar o container zera os contadores |
| Todo mundo é freado junto, atrás de um proxy | o shield vê o IP do proxy para todo cliente | defina `FORWARDED_ALLOW_IPS=<ip do proxy>` ([OPERACAO.md](OPERACAO.md#6-além-do-localhost)) |
| Deslogou sozinho | a sessão expirou (`SESSION_TTL_HOURS`, 12 h), a senha mudou, o usuário foi desativado, ou o `SESSION_SECRET` mudou | entre de novo |
| `sem servidor ou token: rode roqueshield login --server URL, ou defina ROQUESHIELD_URL e ROQUESHIELD_TOKEN`, código 2 | a CLI fora do container não tem configuração | `roqueshield login --server <url>`, ou as duas variáveis no CI |
| `sem conexão com o RoqueShield: ConnectError: ...`, código 2 | endereço errado, ou o shield está fora do ar | confira a URL e `curl <url>/health` |
| `a API recusou (401): ...` | token errado, revogado ou de usuário desativado | crie um token novo em **Usuários** |

## 3. Disparar um scan

A tela de **Novo scan** confere o alvo no primeiro passo e explica o bloqueio ali. A CLI e a API recebem o mesmo motivo em texto, depois de `a API recusou (403): target.value rejeitado:`.

| O que aparece | Causa | O que fazer |
| --- | --- | --- |
| **localhost aqui é o próprio RoqueShield** / `é loopback (dentro do container, o próprio RoqueShield) e só vira alvo com o próprio endereço na allowlist` | dentro do container, `localhost` e `127.0.0.1` são o RoqueShield, não o seu computador | para uma aplicação na sua máquina, use `host.docker.internal` (o botão **Usar host.docker.internal** troca) e libere esse host |
| **Endereço da rede interna** / `em rede privada/loopback/IMDS e nao esta em TARGET_ALLOWLIST` | `LAB_ONLY=true` e o host resolve para endereço privado | um admin libera (**Liberar {host} no escopo**, ou **Escopo**). Quem não é admin pede a um admin. Libere só o que você tem autorização para testar |
| **Não encontrei esse endereço** / `nao resolve em DNS` | o nome não resolve dentro do container. É recusado de propósito: sem resolver, ele poderia apontar para qualquer lugar | confira a grafia e o DNS do container. Nome de container só resolve se os dois estiverem na mesma rede Docker (`docker network connect`) |
| `é link-local (o metadata da nuvem) e não pode ser alvo` | `169.254.169.254` ou a faixa link-local | nenhuma configuração abre este |
| O campo do escopo está travado: **O escopo deste container vem da variável TARGET_ALLOWLIST** | a lista vem do ambiente | mude a variável de ambiente e recrie o container |
| `authorization_ref e obrigatorio (REQUIRE_AUTH_REF=true)`, HTTP 403 | o deploy exige número de ticket ou contrato em todo scan | preencha a **Referência de autorização**, ou `--auth-ref` na CLI |
| `limite de 20 chamadas por minuto em ...`, HTTP 429 | `RATE_LIMIT_PER_MINUTE` por usuário e rota | espere um minuto; aumente a variável se uma pipeline precisa mesmo de mais |
| `target.value nao pode comecar com '-'` | um valor que um scanner leria como opção | corrija o alvo |
| `scheme '...' nao permitido (apenas http/https)` | `file://`, `gopher://` e parecidos | só http ou https |

## 4. Ler o resultado

| O que aparece | Causa | O que fazer |
| --- | --- | --- |
| **Cobertura incompleta** | pelo menos um scanner não rodou; ele está em `scanners_skipped` com o motivo | o cartão **Cobertura** do **Resumo** e a aba **Execução** dizem qual e por quê. Conserte a causa e rode de novo. Não leia o zero achado desse scanner como limpo |
| `zap` pulado, ou o ZAP parou no meio | quase sempre memória: abaixo de 6 GB o kernel mata o ZAP | dê 6 GB ao Docker ([OPERACAO.md](OPERACAO.md#8-memória)) |
| `o ZAP não rastreou NENHUMA URL sob o alvo: nada foi verificado` | o alvo está fora do ar, bloqueado por `robots.txt` ou WAF, ou é uma aplicação só de JavaScript | confira se o alvo responde de dentro do container; para aplicação de página única, o perfil **Completo** |
| `zap não alcançou <url> (accessUrl falhou duas vezes: ...)` | o alvo está fora do ar ou não é alcançável do container | teste de dentro: `docker exec roqueshield python -c "import urllib.request as u; print(u.urlopen('<url>').status)"` |
| `<scanner>: falhou: ...` na lista de pulados | o scanner quebrou | o erro está na aba **Execução** e em `docker exec roqueshield roqueshield logs worker` |
| O scan está em **Falhou** | a esteira falhou antes de terminar; o **Resumo** mostra a fase e o motivo | leia o motivo; `roqueshield scan show <id> --json` tem o campo `errors` |
| Levou muito mais que 13 minutos | um alvo maior, ou o perfil **Completo**, que acrescenta o active scan do ZAP | normal no **Completo**. A CLI desiste de esperar depois de `--prazo` (7200 s) e sai com código 3; o scan continua rodando |
| A CLI saiu com código 3 | o scan falhou, a cobertura veio incompleta, ou o `--wait` estourou o prazo | o 3 vence o 0 e o 1 de propósito: zero achado de scanner que não rodou nunca sai 0 |
| O perfil **Rede** rodou só o nmap | é o que ele roda hoje, para host, porta, domínio ou URL | a descrição do perfil na tela fala em "checagens de rede"; não há nenhuma além do nmap |
| Um alvo web no perfil **Web** não rodou o nmap | para URL ou domínio, o **Web** roda ZAP e nuclei; o nmap só para alvo **Host / IP** | use **Host / IP**, ou **Completo** |

## 5. IA

| O que aparece | Causa | O que fazer |
| --- | --- | --- |
| **IA não configurada** na aba Triagem de IA | sem chave de provedor. O shield não chama modelo nenhum | é opcional. Os achados ficam com a classificação do scanner. Configure um provedor em **IA** para ter triagem e remediação |
| Um erro em cada chamada na **Triagem de IA** | chave, modelo ou endpoint errados, ou o provedor fora do ar | o erro é por chamada. Confira a chave em **IA**; `docker exec roqueshield roqueshield status` mostra `llm_local` e `llm_cloud` |
| Modelo local configurado, mas não é usado | `LLM_API_BASE` vazio (o gateway vai para a nuvem), o nome do modelo diferente do carregado no LM Studio, ou o container não alcança o host | ponha o endpoint `http://host.docker.internal:1234/v1`, copie o nome do modelo exatamente, e confira `llm_local: ok` no `status` |
| O modelo local falha e a triagem falha, com `llm.cloud_fallback_blocked` no log | `ALLOW_CLOUD_FALLBACK=false` proíbe mandar os achados para um modelo de nuvem quando o local falha | é o pretendido em ambiente regulado. Conserte o modelo local; não ligue a variável para o erro sumir |
| Um modelo de raciocínio (Qwen 3, DeepSeek R1) devolve resposta vazia | gastou os tokens pensando antes de responder | aumente os limites de contexto e de saída no LM Studio |
| A investigação só planeja e nunca executa comandos | `AGENT_LIVE_EXECUTION=false`, o padrão | é o pretendido. Ligar deixa um admin executar de verdade os comandos planejados |

## 6. O próprio container

O log do container é o do supervisor: as linhas começam com `[supervisor]`, seguidas da saída de cada processo.

| O que aparece | Causa | O que fazer |
| --- | --- | --- |
| `[supervisor] a migração falhou; a API não sobe sem o schema`, e o container sai | o `alembic upgrade head` falhou: banco de uma versão desconhecida, disco cheio, Postgres que não aceita o login | leia as linhas do alembic logo acima. Não apague o volume para "consertar": faça backup antes ([OPERACAO.md](OPERACAO.md#3-backup-e-restauração)) |
| `Boot recusado por config insegura: APP_TOKEN está com um valor de exemplo/vazio` | um `APP_TOKEN` como `dev-changeme` ou `changeme` veio do ambiente | defina um forte (`openssl rand -hex 32`), ou tire a variável para o container gerar o dele |
| `Boot recusado ...: REQUIRE_IMMUTABLE_AUDIT=true mas o banco é SQLite` | a trilha de auditoria só é append-only no Postgres | aponte o `DATABASE_URL` para um Postgres, ou desligue a exigência de propósito |
| `[supervisor] <processo> saiu com código N`, de novo e de novo | um processo cai e o supervisor reinicia, esperando até 60 s | as linhas anteriores dizem por quê; `docker exec roqueshield roqueshield logs <processo>` |
| Aviso `audit.mutable_trail` em todo boot | o SQLite padrão: a trilha de auditoria pode ser editada | esperado no standalone. Para uma trilha que se sustente em auditoria, o compose de produção |
| A aba **Execução** não mostra log | os logs chegam à aba pelo Redis; o Redis caiu | o `docker logs roqueshield` tem tudo; reinicie o container |
| Perdi a `SECRETS_KEY` (restaurei sem ela, ou troquei) | a chave de IA guardada não pode mais ser decifrada | digite a chave de IA de novo em **IA** |

## 7. Compose de produção

| O que aparece | Causa | O que fazer |
| --- | --- | --- |
| `error while interpolating services.shield.image: required variable SHIELD_VERSION is missing a value: defina SHIELD_VERSION (ex. v0.5.0)` | o compose não achou o `.env`, ou a variável não está nele | sempre `--env-file .env`: com `-f`, o compose procura o `.env` em `docker/`, não na raiz |
| `required variable POSTGRES_PASSWORD is missing a value`, e o mesmo para `REDIS_PASSWORD`, `APP_TOKEN`, `SESSION_SECRET`, `SECRETS_KEY` ou `ZAP_API_KEY` | todas são obrigatórias (`:?`) | gere no cofre e ponha no `.env` |
| A chave de IA não grava, ou o worker não consegue ler | a `SECRETS_KEY` não é uma chave Fernet | gere com `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| O `/health` ainda responde a versão antiga depois de atualizar | o container `shield` não foi recriado, ou a migração falhou | `docker compose ... ps` e o log do serviço `shield` |
| Os scans se acumulam em **Na fila** | nenhum worker rodando, ou os workers não alcançam o Redis | `docker compose ... ps worker`, o log do worker, e o `REDIS_PASSWORD` igual em todos os serviços |

## 8. Resposta a incidente

### Um scan pode ter tocado um alvo fora do escopo

1. **Pare na hora:** `docker stop roqueshield` (em produção, `docker compose ... stop worker shield`). Isso mata os scans em andamento.
2. **Veja o que rodou, contra o quê, por quem.** No standalone, o SQLite está no volume:

   ```bash
   docker start roqueshield
   docker exec roqueshield python -c "import sqlite3; c=sqlite3.connect('/data/shield.db'); [print(*r) for r in c.execute('select s.created_at, t.value, s.state, s.actor, s.authorization_ref from scans s left join targets t on t.id = s.target_id order by s.created_at desc limit 50')]"
   docker exec roqueshield python -c "import sqlite3; c=sqlite3.connect('/data/shield.db'); [print(*r) for r in c.execute('select created_at, actor, action, authorization_ref from audit_log order by created_at desc limit 50')]"
   ```

   Em produção, as mesmas consultas com `psql` no serviço `postgres`. Lá o `audit_log` é append-only: ninguém, nem admin, reescreveu depois do fato.
3. **Avise o dono do engagement**, com a lista de scans e alvos, com transparência. Não rode mais nada até ele decidir.

### Um achado expôs dado pessoal ou credencial

1. Não rode mais scans contra esse ativo até o dono decidir.
2. Avise o dono do engagement. É ele quem decide se há obrigação de notificar um regulador.
3. O AI Fix Bundle passa pelo scrubber, e os relatórios exportados pela tela também, porque são montados a partir dele: credenciais e dados pessoais da evidência saem redigidos. O relatório HTML do servidor (`/reports/<id>`, `roqueshield report --format html`) e o banco **não**: guardam o achado como o scanner devolveu. Compartilhe o bundle ou uma exportação da tela, não o HTML, e trate o volume e os backups dele com o mesmo cuidado que o dado encontrado.

## 9. Onde olhar

```bash
docker logs roqueshield                                   # o supervisor e cada processo
docker exec roqueshield roqueshield status                # versão, conta, cada dependência
docker exec roqueshield roqueshield logs worker --tail 200
docker exec roqueshield roqueshield scan show <scan_id> --json
curl -s http://localhost:8080/health
```

E a aba **Execução** do scan, que tem os mesmos logs com a CPU e a memória de cada processo. Se nada disso explicar, abra uma issue com a versão (`/health`), o sintoma e as linhas de log relevantes, depois de tirar o que identifica o seu alvo: [CONTRIBUTING.md](CONTRIBUTING.md). Problema de segurança no próprio RoqueShield vai pelo [SECURITY.md](../../SECURITY.md), não por issue.
