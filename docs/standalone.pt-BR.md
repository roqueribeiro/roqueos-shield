# RoqueShield standalone

O RoqueShield inteiro num container: o motor e os scanners, a tela, a API REST com
Swagger, o servidor MCP, o Redis e o OWASP ZAP. Sem RoqueOS.

```bash
docker run -d --name roqueshield \
  -p 8080:8080 --shm-size=1g \
  -v roqueshield:/data \
  roqueribeiro1988/roqueos-shield:<versão>-standalone
```

Abra `http://localhost:8080`. A primeira tela cria a conta de administrador; depois
dela, é tela de login. API e Swagger ficam em `/docs`.

## O que roda dentro

| Processo | O que é | Exposto |
| --- | --- | --- |
| `orchestrator` | API, tela, Swagger, MCP por HTTP, progresso ao vivo (SSE) | `:8080` |
| `worker` | roda os scans (nmap, ZAP, nuclei, trivy, semgrep, gitleaks, trufflehog, checkov…) | não |
| `redis` | a fila dos jobs | só `127.0.0.1` |
| `zap` | o daemon do OWASP ZAP e o Firefox headless do AJAX spider | só `127.0.0.1` |

Um supervisor pequeno, em Python, sobe os quatro, reinicia quem cair (1s, 2s, 4s…
até 60s) e para todos em ordem no `docker stop`. Roda como UID 1000; o container não
precisa de capability nenhuma.

Tudo o que a aba **Execução** mostra (o log de cada processo, CPU e memória) vem de
dentro do container. Não há socket do Docker montado.

## Primeiro boot e segredos

Sem `APP_TOKEN`, `SESSION_SECRET`, `SECRETS_KEY` e `ZAP_API_KEY` no ambiente, o
primeiro boot gera os quatro em `/data/secrets` (modo 0600) e reaproveita depois. O
valor nunca é impresso: o log diz só `gerado`, `arquivo` ou `ambiente`. O que vier no
ambiente vence.

A chave do provedor de IA digitada em **Ajustes → IA** é guardada cifrada com a
`SECRETS_KEY` e nunca volta para o navegador.

## Memória

O AJAX spider e o active scan do ZAP são a parte faminta. Dê ao container pelo menos
**6 GB de RAM** livres de verdade. No Docker Desktop isso é a VM, não o notebook: com
menos, o kernel mata o ZAP no meio do scan e o relatório diz isso — `zap` aparece em
`scanners_skipped` e a cobertura fica incompleta. Não vira "zero achado".

## Tudo pelo ambiente

O ambiente vence a tela. Campo definido por variável aparece travado na tela como
"definido pelo ambiente", que é o que um ambiente regulado precisa.

| Variável | Padrão neste container | Efeito |
| --- | --- | --- |
| `DATA_DIR` | `/data` | segredos, SQLite, relatórios, sessão do ZAP, cache do trivy |
| `DATABASE_URL` | SQLite em `/data` | aponte para Postgres para ter trilha de auditoria imutável |
| `REDIS_URL` | embutido | apontando para fora, o Redis embutido não sobe |
| `ZAP_BASE_URL` | embutido | apontando para fora, o ZAP embutido não sobe |
| `LAB_ONLY`, `TARGET_ALLOWLIST`, `REQUIRE_AUTH_REF` | pela tela | travam o escopo autorizado |
| `LLM_MODEL`, `ANTHROPIC_API_KEY`… | pela tela | travam a configuração de IA |
| `ALLOW_CLOUD_FALLBACK` | `true` | `false` proíbe o modelo local de cair num de nuvem |
| `MCP_ALLOW_ACTIONS` | `false` | deixa cliente MCP disparar scan (sempre com referência de autorização) |
| `OIDC_*` | desligado | SSO, ao lado do login por senha |

Para produção, `docker/compose.prod.yml` roda a mesma imagem com Postgres, Redis e ZAP
em serviços separados.

## CLI

`roqueshield` fala com um shield rodando, pela API. Dentro do container:

```bash
docker exec roqueshield roqueshield status
```

De qualquer outro lugar, com um token criado em **Usuários**:

```bash
roqueshield login --server http://shield:8080        # pergunta o token, sem eco
roqueshield scan start https://app.exemplo --auth-ref CHG-123 --wait --fail-on high
roqueshield report <scan_id> --format bundle -o bundle.json
```

Códigos de saída para pipeline: `0` terminou e está limpo no limite, `1` achado no
`--fail-on` ou acima, `2` erro de uso ou de conexão, `3` o scan falhou ou a cobertura
veio incompleta. O `3` vence: zero achado de scanner que não rodou nunca sai `0`.
`ROQUESHIELD_URL` e `ROQUESHIELD_TOKEN` substituem o `login` no CI.

## MCP

Para Claude Code, Claude Desktop ou Cursor, por stdio:

```bash
claude mcp add roqueshield -- roqueshield mcp
```

Ou por HTTP, `POST /mcp` com o cabeçalho `X-API-Token`. Ferramentas: `list_scans`,
`get_scan`, `get_findings`, `get_ai_bundle`, `list_targets`, e `start_scan` só com as
ações ligadas. Scan que falhou ou veio incompleto volta como erro com o motivo, nunca
como lista vazia.
