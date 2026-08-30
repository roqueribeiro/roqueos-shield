<div align="center">
<img src="assets/logo-roqueos.png" alt="RoqueOS" width="72" />

# RoqueShield — a arquitetura, nível a nível

</div>

Nove diagramas, seguindo o [modelo C4](https://c4model.com) nos quatro primeiros
níveis e depois indo onde o C4 não vai: infraestrutura, a esteira do scan, a coleira
do agente, as superfícies de integração e a interface do produto.

Toda figura é **gerada a partir de código** em [`../scripts/diagrams/`](../scripts/diagrams/)
e regerada por `python scripts/gen_diagrams.py`. Toda caixa nomeia um módulo,
container ou arquivo real — nada aqui descreve capacidade que não esteja no
repositório, e onde a capacidade é parcial o diagrama diz que é parcial.

> **Regra de leitura:** se um diagrama e o código discordarem, o código ganha e o
> diagrama é que precisa ser corrigido — na mesma entrega.

---

## Nível 1 — Contexto

*Quem usa, o que a plataforma varre, de quem depende. No nível 1 o RoqueShield é uma
caixa só; a decomposição é o nível 2.*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/c1-context-dark.svg">
  <img alt="C1 — Contexto do sistema" src="assets/diagrams/c1-context-light.svg">
</picture>

Três tipos de ator chegam ao sistema, e o terceiro é o que muda o desenho da
ferramenta. Um **operador de segurança** registra o alvo, declara a autorização e
assina o relatório. Um **time de desenvolvimento** recebe achado já triado sem nunca
abrir a ferramenta. Um **agente de IA** lê o AI Fix Bundle, corrige o código e pede
outro scan — que é por que o bundle é um contrato versionado, e não uma página
renderizada.

---

## Nível 2 — Containers

*Cada caixa é um processo com imagem própria. Tudo dentro da fronteira sobe como uma
stack Docker só.*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/c2-containers-dark.svg">
  <img alt="C2 — Containers" src="assets/diagrams/c2-containers-light.svg">
</picture>

A separação que importa é **orchestrator contra worker**: a mesma imagem com
entrypoint diferente. O orchestrator responde HTTP e transmite SSE; o worker roda
`arq` e é o processo que de fato executa adapters, chama o LLM e escreve o relatório.
É isso que permite ao `POST /scans` devolver `202` em milissegundos enquanto o scan
leva meia hora.

Repare no que o diagrama marca em vermelho: `cai-expert` é um **stub declarado**. O
compose diz isso no próprio cabeçalho, e o Dockerfile termina a instalação com
`|| true`, então a imagem sobe mesmo quando a instalação falha.

---

## Nível 3 — Componentes

*O que vive dentro da imagem que o orchestrator e o worker compartilham.*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/c3-components-dark.svg">
  <img alt="C3 — Componentes" src="assets/diagrams/c3-components-light.svg">
</picture>

Dois detalhes deste nível merecem parada.

`jobs/pipelines.py` guarda três coisas que costumam ficar espalhadas: a resolução de
scanner (`resolve_scanners`, precedência **pedido explícito > profile > default do
tipo de ativo**), a factory (`_build_adapters`, nove entradas) e o ciclo de vida
(`_run_adapter`). Mantê-las juntas é o motivo de a conversão de `coverage_gaps` em
achado INFO acontecer em exatamente um lugar. Quinze adapters lembrarem de fazer isso
seria convenção; um lugar é mecanismo.

`jobs/exposure.py` **não** passa pela factory — instancia seis adapters direto. É
assim que um scanner pode existir, ter teste, e nunca ser construído por nenhum
caminho de produção; dois deles estão exatamente nesse estado hoje.

---

## Nível 4 — Código: o ciclo de vida do scanner

*Cada passo tem uma saída de erro explícita, e nenhuma delas devolve lista vazia.*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/c4-code-dark.svg">
  <img alt="C4 — Ciclo de vida do adapter e o contrato do silêncio" src="assets/diagrams/c4-code-light.svg">
</picture>

É o nível em que a regra que governa o projeto vira código. `health()` precisa fazer
round-trip de verdade, porque construir um cliente de SDK não prova nada sobre uma
credencial. `poll()` precisa ler `task.result()`, porque processo que terminou não é
processo que deu certo. `fetch_results()` precisa levantar exceção com report
ausente, vazio ou ilegível, porque `{}` e "o repositório está limpo" são o mesmo
JSON.

E a execução da regra não é hábito de code review: `scripts/check_no_silence.py` lê a
AST e reprova o build. Ele mesmo foi endurecido depois que uma auditoria adversarial
contornou a primeira versão de quatro formas — as quatro hoje são
`tests/unit/test_gate_do_silencio.py`.

---

## Infraestrutura e implantação

*Dois jeitos de subir, uma imagem.*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/infra-deploy-dark.svg">
  <img alt="Infraestrutura e implantação" src="assets/diagrams/infra-deploy-light.svg">
</picture>

Sob o RoqueOS, **nenhuma porta do RoqueShield é publicada no host**: o orchestrator é
alcançável só pela rede interna do Docker, e a única entrada é o proxy reverso do
RoqueOS, que injeta o token server-side. Autônomo, a `8080` é publicada e o `/ui` fica
acessível direto — o que é a troca certa para máquina de desenvolvimento e a errada
para servidor.

A imutabilidade da trilha de auditoria é um **trigger do Postgres**, não disciplina de
aplicação. Em SQLite o trigger não existe, e o `main.py` loga `audit.mutable_trail`
para dizer isso em voz alta em vez de deixar um ambiente de teste fingir calado.

---

## A esteira do scan

*Do POST ao relatório.*

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/esteira-scan-dark.svg">
  <img alt="A esteira de um scan" src="assets/diagrams/esteira-scan-light.svg">
</picture>

Três portões rodam antes de um único pacote sair: escopo, autorização, auditoria. O
terceiro grava `scan.create` na trilha **no mesmo commit** que cria a linha do scan —
ou os dois existem, ou nenhum, então não há scan sem registro de quem pediu.

Uma decisão de ordem é deliberada e parece errada à primeira vista: o relatório é
renderizado **antes** de os achados serem persistidos. O caminho do relatório precisa
existir para entrar na linha do scan, e sem essa ordem o `GET /reports/{id}` devolvia
404 para sempre.

E o estado final não é cosmético: quando **nenhum** scanner rodou, o scan termina
`FAILED`, não `DONE` com zero achados.

---

## O sidecar Kali e o agente dentro dele

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/kali-cai-agente-dark.svg">
  <img alt="Kali toolbox e a coleira do agente" src="assets/diagrams/kali-cai-agente-light.svg">
</picture>

Dezenove ferramentas, escolhidas uma a uma — a base é `kali-rolling`, não
`kali-linux-large`, porque o metapacote grande passa de 12 GB de ferramenta que
ninguém chama.

A coleira são quatro checagens no `executor.py`, e a terceira é a que fecha a classe
inteira de fuga por prompt injection: o comando é entregue ao
`asyncio.create_subprocess_exec` como **lista de argv**, nunca como string de shell.
Não existe metacaractere para o modelo escapar, porque não existe shell para escapar.

---

## Superfícies de integração e o laço do agente

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/integracoes-agente-dark.svg">
  <img alt="Superfícies de integração e o laço do agente" src="assets/diagrams/integracoes-agente-light.svg">
</picture>

Detalhe completo em [integrations.pt-BR.md](integrations.pt-BR.md). Em resumo: três
superfícies existem hoje — CLI, REST e o AI Fix Bundle — e bastam para montar o laço
scan → conserto → re-scan. O servidor MCP e a GitHub Action da faixa de baixo são
**propostas, não funcionalidades.**

---

## A interface do produto dentro do RoqueOS

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/diagrams/telas-roqueos-dark.svg">
  <img alt="Telas do RoqueShield dentro do RoqueOS" src="assets/diagrams/telas-roqueos-light.svg">
</picture>

> **São diagramas de interface, não capturas de tela.** Nenhuma captura da UI rodando
> existe neste repositório; quando existir, ela substitui a figura e esta nota sai.

O app é admin-only, aparece no Launchpad do RoqueOS só quando a capability `pentest`
está ligada, e abre numa janela de 1280×860. Quatro seções mais o detalhe de um scan.
Dois comportamentos merecem nome porque são decisão de segurança, não de UI:

- O stepper do detalhe é movido por **SSE** com uma rede de polling de 4 s por baixo,
  porque um stream que não sobe não pode deixar o operador olhando barra de progresso
  congelada.
- O stream carrega um **session-token curto na query string** — nunca a apiKey —
  porque `EventSource` não manda header, e credencial em URL acaba em todo log de
  proxy no caminho.

---

## Como estes diagramas continuam verdadeiros

```bash
python scripts/gen_diagrams.py           # regenera os 18 SVGs
python scripts/gen_diagrams.py --check   # reprova se algum estiver atrasado, faltando ou órfão
```

O `--check` roda no CI. Ele compara o SVG em disco com o que o código produz agora, e
reprova em três condições: arquivo alterado à mão, arquivo faltando, e arquivo na
pasta que nenhum módulo gera. Testado por mutação — os três plantios saem 1, e a
árvore limpa sai 0.

O gerador não depende de nada fora da biblioteca padrão. A medida de texto vem de
`scripts/diagrams/metrics.json`, uma tabela de avanço por caractere extraída uma vez
das fontes reais e versionada junto do código.

Essa tabela é a terceira tentativa, e as duas que ela substituiu falharam em silêncio.
A primeira estimava largura por balde de caractere, errava cerca de 7 % para baixo e
produzia caixa com texto vazando no render — defeito que só aparece olhando a saída. A
segunda media com a fonte instalada, consertou o vazamento e trouxe um problema pior: a
mesma entrada gerava SVG diferente em máquina sem a Inter, e o `--check` reprovava por
causa da máquina, não por causa do desenho. Transformar medida em aritmética eliminou
os dois.
