#!/bin/sh
# Monta o ruleset OFFLINE do semgrep em $1 (padrão /opt/semgrep-rules).
#
# Um script só para a imagem (docker/images/orchestrator/Dockerfile) e para o CI
# (job regua-deteccao): a régua do CI media o SAST com os packs do registry
# (p/security-audit...) enquanto a produção rodava este ruleset podado. Dois conjuntos
# de regras, duas medidas, e a régua não dizia nada sobre o que roda de verdade.
#
# POR QUE EMBARCAR: o default `--config p/security-audit` baixa as regras do registry
# da Semgrep a cada scan. Num banco a rede é restrita, e sem alcançar o registry o
# semgrep sai com código 0, ZERO regras e zero achados: o silêncio clássico.
#
# Só os diretórios por linguagem, validados um a um: a RAIZ do repo tem config
# inválida, e passar a raiz faz o semgrep abortar com "1 configs were invalid" e zero
# regras. O --validate é gate: se um diretório quebrar numa atualização do pin, sai 1.
# elixir fica de fora: exige extensão proprietária que não vem no open source.
set -eu

COMMIT="40b8c63f75dc7c22c8a77482d73bfb864b146f7e"
DESTINO="${1:-/opt/semgrep-rules}"
SRC="$(mktemp -d)"

git init -q "$SRC"
git -C "$SRC" remote add origin https://github.com/semgrep/semgrep-rules.git
git -C "$SRC" fetch -q --depth 1 origin "$COMMIT"
git -C "$SRC" checkout -q FETCH_HEAD

mkdir -p "$DESTINO"
for d in python javascript typescript java go ruby php csharp terraform \
         dockerfile bash rust kotlin swift scala yaml json html c ocaml \
         clojure generic; do
    cp -r "$SRC/$d" "$DESTINO/"
done
find "$DESTINO" -type d -name .semgrep_logs -prune -exec rm -rf {} +

# Só o que é SEGURANÇA. Os diretórios por linguagem trazem também boa prática,
# desempenho, manutenção, correção e compatibilidade: achado MEDIUM de "use
# raise_for_status" num código correto. A régua noturna do shield central pegou isso
# em 19/11/2026: falso positivo num controle limpo do gabarito.
for cat in best-practice best-practices performance maintainability correctness \
           compatibility portability caching; do
    find "$DESTINO" -type d -name "$cat" -prune -exec rm -rf {} +
done

# Sair de $SRC antes de apagar: um semgrep rodado com cwd inexistente morre em
# Semgrep_envvars.of_current_sys_env com Sys_error("No such file or directory").
cd /
rm -rf "$SRC"

for d in "$DESTINO"/*/; do
    semgrep --validate --config "$d" --metrics off --disable-version-check
done
echo "$COMMIT" > "$DESTINO/PINNED_COMMIT"
