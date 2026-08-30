<div align="center">
<img src="assets/logo-roqueos.png" alt="RoqueOS" width="72" />

# RoqueShield — agentes, APIs e esteiras

</div>

Como dirigir o RoqueShield a partir de algo que não é humano: um agente de IA, um
serviço, um job de CI. O que existe hoje está na primeira metade; o que não existe
está na segunda, rotulado, com o que falta para construir.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/integracoes-agente-dark.svg">
  <img alt="Superfícies de integração e o laço do agente" src="assets/diagrams/integracoes-agente-light.svg">
</picture>

---

## 1. As três superfícies que existem

### CLI — `cai`

Uma aplicação Typer, quatro comandos, rodando **in-process**: sem API para subir, sem
token para gerenciar. É o caminho mais curto para um agente que já tem shell.

```bash
cai scan https://staging.exemplo.com --asset-type url --criticality high
cai scan git@github.com:acme/api.git --asset-type repo
cai exposure "Acme Corp" --domains acme.com --github-orgs acme
cai bundle 8f2c1e4a-... --out bundle.json
cai serve --host 0.0.0.0 --port 8080
```

`--skip-ai` roda o scan sem a etapa de triagem, que é o que você quer quando o LLM
está fora e você ainda precisa de cobertura.

### REST — FastAPI, 33 rotas

OpenAPI em `/docs`. Autenticação por `X-API-Key` + `X-API-Secret`, ou OIDC. As rotas
que uma integração de fato usa:

| Passo | Chamada |
| --- | --- |
| Registrar o alvo | `POST /targets` → `201` |
| Disparar o scan | `POST /scans` → `202` com o id |
| Acompanhar | `GET /scans/{id}` — ou o stream, abaixo |
| Ler os achados | `GET /findings?scan_id=…` |
| Postura de compliance | `GET /reports/{id}/compliance` |
| O bundle | `GET /reports/{id}/ai-bundle` |

Progresso ao vivo é `GET /ui/api/events`, `text/event-stream`, emitindo eventos
`phase` e `log`. `EventSource` não manda header, então esse endpoint recebe um
**session-token curto na query string** — nunca a apiKey, que aí viveria em todo log
de proxy do caminho.

### AI Fix Bundle — o contrato para máquina

`GET /reports/{scan_id}/ai-bundle`, schema `1.0.0`, especificado em
[ai-fix-bundle-spec.md](ai-fix-bundle-spec.md).

É a superfície desenhada para um agente ler: achados já deduplicados e triados, cada
um com id estável, prioridade, arquivo e linha, CWE, evidência e remediação sugerida.
Tem **versão de schema** porque quem consome precisa saber quando muda — o sentido de
um contrato é justamente não ser uma página renderizada que alguém raspa.

> Inconsistência conhecida, não escondida: o bundle emite `"generator": {"tool":
> "cai", "version": "0.3.0"}` enquanto a aplicação declara `0.4.0` e o
> `pyproject.toml` diz `0.1.0`. Hoje um consumidor não consegue dizer qual build
> gerou um bundle. O conserto é ler de uma fonte só; está registrado, não feito.

---

## 2. O laço: scan → conserto → re-scan

As três superfícies acima bastam para fechar o laço sem pessoa no meio.

1. **Scan.** O agente dispara o scan no repositório, imagem ou URL de staging.
2. **Bundle.** Lê `GET /reports/{id}/ai-bundle` — estruturado, não raspado.
3. **Conserto.** Edita o código com o CWE e a remediação sugerida como contexto.
4. **Re-scan.** Dispara um novo scan sobre o código corrigido. *É o passo que separa
   conserto de alegação de conserto.*
5. **Comparação.** Casa os dois scans por `deduped_key`: o que sumiu foi corrigido, o
   que ficou volta ao passo 3, e o que é **novo** é regressão que o patch criou.

### O critério de parada

Não é "o agente relatou sucesso". O laço acaba quando o scan seguinte não acha o que o
anterior achou **e** o `coverage_complete` continua verdadeiro.

Essa segunda condição não é decoração. Um scanner que deixou de rodar entre as
rodadas — rede que fechou, container que não subiu, credencial que expirou — produz
zero achados pelo mesmo motivo que um código limpo produz. Sem conferir cobertura, "o
agente consertou tudo" e "o scanner parou de funcionar" são indistinguíveis, e o laço
declararia vitória em cima de uma ferramenta quebrada. É a mesma falha que o projeto
inteiro existe para impedir, entrando pela porta da frente.

Uma implementação correta do passo 5 confere três coisas, nesta ordem:

```python
assert novo["coverage_complete"], "scanner deixou de rodar; comparação inválida"
assert set(novo["scanners_ran"]) >= set(anterior["scanners_ran"])
resolvidos = anterior_keys - novo_keys
regressoes = novo_keys - anterior_keys
```

### Um exemplo com a CLI

```bash
ANTES=$(cai scan git@github.com:acme/api.git --asset-type repo --json | jq -r .scan_id)
cai bundle "$ANTES" --out bundle.json

# ... o agente corrige o repositório a partir do bundle.json ...

DEPOIS=$(cai scan git@github.com:acme/api.git --asset-type repo --json | jq -r .scan_id)
cai bundle "$DEPOIS" --out bundle-depois.json

jq -s '{
  resolvidos: (.[0].findings - .[1].findings),
  regressoes: (.[1].findings - .[0].findings)
}' bundle.json bundle-depois.json
```

---

## 3. Não implementado: servidor MCP

**Estado: proposta.** Medido em 2026-08-30: zero ocorrência de MCP em qualquer lugar
sob `orchestrator/`. Não há servidor, não há transporte, não há definição de tool. O
que existe e às vezes é confundido com isso: dez *skills* de Claude Code em
`.claude/skills/`, que são instruções de prompt para um editor, não um servidor de
protocolo que outros clientes falam.

As tools que se justificariam — uma por caso de uso que hoje exige shell:

| Tool | Argumentos | Devolve |
| --- | --- | --- |
| `shield_scan` | alvo, asset_type, profile, authorization_ref | id do scan, aceito ou o motivo da recusa |
| `shield_status` | scan_id | estado, fase corrente, progresso |
| `shield_findings` | scan_id, severidade mínima | os achados triados |
| `shield_bundle` | scan_id | o AI Fix Bundle |
| `shield_compare` | scan_a, scan_b | resolvidos, restantes, regressões, delta de cobertura |

**O que falta para construir:** o processo servidor e seu transporte; autenticação por
token de serviço, já que cliente MCP não carrega a sessão do operador; a decisão sobre
se uma tool pode iniciar scan ou só ler — iniciar scan é efeito colateral com peso
jurídico quando o alvo é de terceiro; e um teste provando que toda tool **devolve erro
quando o scan falhou**, em vez de lista vazia. Esse último não é detalhe. Uma tool que
responde `[]` para um scan que nunca rodou reintroduz, na fronteira do protocolo,
exatamente o silêncio que o resto deste projeto gasta dois gates de CI impedindo.

---

## 4. Não implementado: GitHub Action reutilizável

**Estado: proposta.** Medido em 2026-08-30: `.github/workflows/` tem um arquivo só,
`ci.yml`, sem `workflow_call`, e não existe `action.yml` no repositório. Nada aqui
pode ser chamado da esteira de outro projeto hoje.

A forma que teria:

```yaml
# .github/workflows/security.yml, no repositório que consome
jobs:
  roqueshield:
    uses: roqueribeiro/roqueos-shield/.github/workflows/scan.yml@v1
    with:
      target: .
      asset-type: repo
      profile: full
      fail-on: high          # política, e é decisão de produto
    secrets:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

…produzindo o AI Fix Bundle como artefato do build, os achados como anotação do
GitHub nas linhas alteradas, e um comentário no PR com a nota de compliance.

**O que falta para construir:** o `action.yml` e o ponto de entrada `workflow_call`;
uma imagem publicada com **tag estável** para a Action fixar, porque scanner de
segurança que troca de versão calado entre execuções é pior que scanner nenhum; o
mapeamento de `Finding` para o formato de anotação do GitHub; e uma decisão de
política sobre `fail-on` — qual severidade barra o merge — que pertence a quem é dono
do repositório, não a esta ferramenta.

Há mais um requisito, e é o mesmo do MCP: a Action precisa reprovar o build quando um
scanner não rodou. Tique verde num scan com `coverage_complete: false` é a versão CI
do zero silencioso.

---

## 5. Hoje, sem nenhum dos dois

As duas lacunas têm resposta funcionando agora, e é por isso que nenhuma é urgente.

**No CI**, um passo de shell:

```yaml
- name: RoqueShield
  run: |
    docker run --rm -v "$PWD:/src" roqueribeiro1988/roqueos-shield:latest \
      scan /src --asset-type repo --skip-ai > resultado.json
    python - <<'PY'
    import json, sys
    r = json.load(open("resultado.json"))
    if not r.get("coverage_complete"):
        sys.exit("scanner nao rodou por completo; resultado nao e conclusivo")
    altos = [f for f in r["findings"] if f["severity"] in ("critical", "high")]
    if altos:
        sys.exit(f"{len(altos)} achado(s) de severidade alta ou critica")
    PY
```

**Com um agente**, a CLI já é a interface: um agente de código com acesso a shell roda
`cai scan` e `cai bundle` direto. O servidor MCP tornaria isso ergonômico para
clientes sem shell — não destravaria nada que a CLI já não faça.
