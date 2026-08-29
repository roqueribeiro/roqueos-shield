# O contrato do silêncio — a regra e os dois mecanismos que a executam

Um scanner quebrado produz **exatamente a mesma saída** de um alvo seguro: zero
achados. Num relatório que vai para auditoria de banco, essa é a única diferença que
importa — e era a diferença que esta ferramenta não sabia fazer.

Não foi um descuido isolado. Foram **nove adapters**, sempre com a mesma forma:

1. Scanner incompatível com o tipo de alvo levantava `ValueError`, o erro era
   engolido, e o scan de IMAGE/REPO fechava com zero findings.
2. O nuclei, sem `-duc`/`-ni`, tentava a internet e pendurava até o timeout de 1800s
   em rede restrita — que num banco é o caso normal.
3. O semgrep com um `--config` que não resolve sai com código 0, **zero regras** e
   zero achados. Pior: o default era `auto`, **incompatível com o `--metrics off`**
   que a postura de soberania deste projeto exige. O único scanner que lê o código
   falhava em 100% das execuções.
4. O checkov recebia a **URL** do repo em `-d`. O checkov loga "Directory does not
   exist; skipping it", sai com código 0 e escreve saída **vazia**. Todo scan de
   REPO com alvo-URL passou por aí: o checkov nunca achou nada em produção, e a tela
   dizia que ele rodou.
5. `gitleaks`, `dnstwist`, `kube_bench`: report ausente ou ilegível virava `{}` →
   "repositório limpo", "sem typosquatting", "cluster em conformidade".
6. `shodan` e `censys` **fabricavam** `{"matches": [], "total": 0}` em qualquer
   exceção — cota estourada, chave inválida, API fora do ar.
7. O `health()` do censys só **construía** o cliente do SDK. Construtor não faz
   round-trip: chave inválida passava no health e a busca falhava depois, calada.
8. O `github_exposure` dava `break` no rate limit e abandonava as dorks restantes.
   Com dez dorks e o limite estourando na terceira, o relatório mostrava três como se
   fossem dez.
9. O ZAP lia a fila passiva vazia como "terminou" sem verificar se o spider rastreou
   **alguma** URL, e lia **uma** página de 500 alertas sem paginar.

## A regra

Ao escrever ou revisar qualquer adapter, a pergunta é sempre:

> **"Zero achados aqui significa *limpo*, ou significa *não rodou*?
> Se não houver como distinguir, falta um sinal."**

Três níveis. O adapter escolhe um — nunca o silêncio:

| Situação | O que fazer | Onde aparece para o usuário |
| --- | --- | --- |
| Rodou e não achou | devolver `[]` | achado nenhum, cobertura completa |
| Não deu para verificar | `raise ScanIntegrityError` | `scanners_skipped`, `coverage_complete: false` |
| Verificou em parte | preencher `RawResults.coverage_gaps` | achado **INFO** no relatório |

O terceiro nível existe porque o meio-termo antes só virava log — e log ninguém lê.
O `_run_adapter` converte `coverage_gaps` em `Finding` INFO num lugar só, de
propósito: quinze adapters lembrarem disso é convenção; um lugar é mecanismo.

Regras concretas que caíram desta análise:

- **Leia o returncode.** `task.done()` diz que o processo terminou, não que deu
  certo. Adapter de subprocess devolve `(rc, path)` e o `poll` lê `rc`.
- **Use `read_jsonl` (`adapters/base.py`)** em vez de
  `except json.JSONDecodeError: continue`. Toda linha ilegível → reprova; parte
  ilegível → preserva as boas e declara a lacuna.
- **Nunca fabrique payload de sucesso** dentro de um `except`.
- **Cascata precisa de checagem por etapa.** `if arquivo_anterior.exists()` faz a
  primeira falha apagar em silêncio as etapas seguintes.
- **`health()` precisa de round-trip.** Construir cliente de SDK não prova credencial.
- **Paginação é cobertura.** Primeira página devolvida como total é o mesmo silêncio
  com outra roupa: compare com o total reportado e declare a diferença.
- **Ferramenta de rede vai com o egress fechado por padrão** (`-duc`, `-ni`). Sem
  isso ela pendura até o timeout numa rede corporativa — o ambiente normal do alvo
  deste projeto.

## Os mecanismos (senão isto aqui é decoração)

### 1. `scripts/check_no_silence.py` — job **Contrato do silencio** no CI

Compara o **código** com a regra, por AST e não por grep. Reprova quando encontra,
no ciclo de vida do scan (`start_scan`/`poll`/`fetch_results`/`normalize` e as
closures dentro deles):

- `except` que termina em vazio — `return []`, `return {}`, `return RawResults(payload={})`,
  `x = []`, `continue`, `pass` — sem `raise` nem registro de lacuna;
- `poll()` que decide por `task.done()` sem ler `task.result()`;
- dicionário de sucesso fabricado dentro de `except` (o caso do shodan).

Escape explícito, quando o vazio é mesmo o certo: `# silencio-ok: motivo` na linha do
`except`. Nada entra sem o motivo escrito — se um dia um silêncio de verdade for
liberado por uma dessas linhas, o motivo escrito é o que denuncia.

**Teste de mutação, quatro plantios, todos `exit 1`:** `except` devolvendo vazio;
`except` devolvendo vazio **embrulhado** num `RawResults` (a forma que escapou da
primeira versão do gate, e por isso ela foi corrigida antes de entrar); `poll`
decidindo só por `task.done()`; dict de sucesso fabricado. Árvore limpa: `exit 0`.

**E o gate tem gate.** Uma auditoria adversarial burlou a primeira versão de quatro
formas e reintroduziu o silêncio no nmap com o gate em `exit 0` e a suíte verde. As
quatro viraram teste (`tests/unit/test_gate_do_silencio.py`), e o gate foi
endurecido para pegar cada uma:

| burla | por que passava | o que mudou |
| --- | --- | --- |
| `if _ESTRITO: raise` com a flag desligada | qualquer `raise` no `ast.walk` contava | `raise` sob condição constante ou flag em maiúsculas não conta |
| `.append` numa lista local que ninguém lê | bastava um atributo chamado `append` | o destino precisa se chamar `gap`/`erro`/`lacuna`/`errors` |
| silêncio movido para um helper `_ler_report()` | a checagem era por NOME de função | num adapter, **toda** função conta (menos `health`/`cleanup`) |
| `payload=texto if texto.strip() else ""` | não há `except` para o gate reclamar | `fetch_results` que constrói resultado vazio e nunca levanta reprova |

Um controle que o autor do código contorna em quatro tentativas não é controle. E
mesmo assim o gate é o **piso**, não o teto: os testes por adapter e o
`efetividade` continuam sendo o que segura o resto.

### 2. Os testes, que provam os dois lados

- `tests/unit/test_silencio_adapters.py` — a ferramenta **não mente quando falha**.
  Teste de mutação por adapter: reverter o conserto reprova.
- `tests/integration/test_efetividade_e2e.py` — job **efetividade** do CI — a
  ferramenta **acha de verdade**. Sem este, uma ferramenta que só levantasse exceção
  passaria em tudo, porque "0 achados" é o estado natural de um scanner quebrado.
  Monta um repo com defeito conhecido (injeção de comando, SQLi por taint, pickle,
  MD5, debug ligado, bucket S3 público, SG `0.0.0.0/0`, disco sem cifra) e exige
  achado real de cada camada — enquanto confere que o scanner ausente aparece em
  `scanners_skipped`. Mutação confirmada: com o default antigo (`--config auto`) o
  SAST não roda e o gate reprova.

## Quando o gate reclamar

Não silencie: decida em qual dos três níveis o caso está. O `# silencio-ok` é para o
vazio que é mesmo o resultado certo (o `health()`, por contrato, é o único isento) —
não é para pressa.
