# Documentação viva — a regra e o mecanismo que a executa

Este repositório é **público** e é a cara da ferramenta. Quem chega decide em cinco
minutos se confia nela, e decide lendo a documentação. Doc velha não é detalhe
estético: é a ferramenta prometendo o que não faz.

Já aconteceu aqui, e custou caro:

- A UI prometia `web: nmap + ZAP + Nuclei`. O nuclei estava órfão — não entrava na
  fábrica de adapters — e o scan web rodava só ZAP passivo. A promessa era falsa por
  meses, e ninguém viu porque nada comparava a promessa com o código.
- A arquitetura descrevia o agente como "stub" **depois** de o loop agêntico existir.
- Metade dos controles de segurança (`ALLOW_INSECURE_APP_TOKEN`,
  `REQUIRE_IMMUTABLE_AUDIT`, `SESSION_SECRET`) não estava no `.env.example`: opção
  que existe e ninguém sabe ligar é opção que não existe.

## A regra

**Mudança de comportamento sai no mesmo commit que a documentação dela.** Scanner
novo, variável de ambiente nova, contrato com o RoqueShield alterado, capacidade do
agente mudada: o README e/ou `docs/architecture.md` mudam junto. Não em seguida, não
"na próxima" — junto.

## O mecanismo (senão isto aqui é decoração)

`scripts/check_docs_fresh.py`, rodado pelo job **Documentação em dia** no CI. Ele não
lê intenção; compara doc com código e reprova quando divergem:

1. **Scanners** — todo adapter construível em `_build_adapters` precisa aparecer no
   README ou na arquitetura. Scanner que roda e ninguém documenta reprova.
2. **Variáveis** — todo campo de `Settings` precisa estar no `.env.example`.
3. **Afirmações vencidas** — a doc não pode chamar de "stub"/"pendente" o que já é
   código executando (checado contra o código, não contra a prosa: o gate ignora
   `NotImplementedError` citado dentro de comentário).

Teste de mutação, rodado ao criar o gate — os três dão `exit 1`: adapter novo sem
documentar, `Settings` novo sem `.env.example`, e a doc voltando a chamar o agente de
stub. Com a árvore limpa, `exit 0`.

## Quando o gate reclamar

Ele aponta o arquivo e o motivo. A saída é para ser lida, não silenciada: se a
divergência for legítima (a doc está certa e o gate está errado), o conserto é no
gate, com o caso novo virando teste — nunca um `# noqa` na documentação.
