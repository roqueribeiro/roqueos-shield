#!/usr/bin/env python3
"""Gate do contrato do silêncio — regra sem mecanismo é decoração.

O defeito mais caro deste repositório apareceu nove vezes com a mesma forma: um
scanner não roda, o erro é engolido, e o relatório apresenta zero achados como se
fosse alvo limpo. Um scanner quebrado produz a MESMA saída de um alvo seguro, e num
relatório que vai para auditoria essa é a única diferença que importa.

"Sempre trate o erro" é um bom propósito e um péssimo controle: ninguém percebe a
volta do padrão numa revisão de diff. Este script compara o CÓDIGO com a regra e
reprova o merge.

O que ele reprova, em `orchestrator/adapters/`, `orchestrator/jobs/` e
`orchestrator/reporting/exporters/`:

1. `except` no ciclo de vida do scan (start_scan/poll/fetch_results/normalize e as
   closures dentro deles) que termina em vazio — `return []`, `return {}`,
   `x = []`, `continue`, `pass` — sem `raise` nem registro de lacuna.
2. `poll` que decide por `task.done()` sem ler `task.result()`: "o processo
   terminou" não é "o processo deu certo".
3. Fabricação de payload de sucesso dentro de `except` (dicionário com chaves de
   resultado e valores vazios) — o caso do shodan, que inventava
   `{"matches": [], "total": 0}` quando a API recusava a chave.
4. `_persist_findings` que não grava a cobertura. Nenhuma regra de `except` pegaria
   este: o defeito é uma atribuição que NÃO EXISTE. O pipeline calculava
   `scanners_skipped` certinho e a persistência escrevia só `state=DONE`, então um
   scan em que nada rodou chegava à API como `done`, `errors: []`,
   `coverage_complete: true`. O gate anterior era cego para isso porque só olhava
   `adapters/` — a camada que TRANSPORTA o sinal ficava sem controle.

Escape explícito, quando o vazio é mesmo o certo: comentar `# silencio-ok: motivo`
na linha do `except`. O motivo escrito é o que denuncia um abuso na revisão.

Uso: python scripts/check_no_silence.py   (exit 1 quando há violação)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_ADAPTERS = RAIZ / "orchestrator" / "adapters"

# O gate nasceu olhando SÓ `adapters/`, e uma auditoria mostrou que os piores casos
# estavam fora: o pipeline calculava a cobertura certinho e o `_persist_findings` não
# a gravava, então tudo morria no worker. Consertar o adapter e deixar a camada que
# TRANSPORTA o sinal sem gate é meio caminho.
DIRS_EXTRA = [
    RAIZ / "orchestrator" / "jobs",
    RAIZ / "orchestrator" / "reporting" / "exporters",
]

# Funções onde um silêncio vira "alvo limpo" no relatório.
CICLO_DE_VIDA = {
    "start_scan",
    "poll",
    "fetch_results",
    "normalize",
    "health",
    "_run",
    # A camada que carrega a cobertura do pipeline até a tela.
    "run_scan",
    "run_exposure_scan",
    "_run_adapter",
    "_persist_findings",
    "_coverage",
    "build_bundle",
}
MARCA_ESCAPE = "silencio-ok"

# `health()` é o único que PODE devolver vazio calado: o contrato dele é retornar
# bool sem lançar, e o pipeline já trata False como cobertura incompleta.
ISENTAS = {"health"}


def _vazio(no: ast.AST) -> bool:
    """True para literal de coleção vazia (`[]`, `{}`, `()`, `""`, `0`)."""
    if isinstance(no, ast.List | ast.Tuple | ast.Set):
        return not no.elts
    if isinstance(no, ast.Dict):
        return not no.keys
    if isinstance(no, ast.Constant):
        return no.value in ("", 0, None) or no.value is None
    return False


def _dict_de_sucesso_falso(no: ast.AST) -> bool:
    """Dicionário com chaves de resultado e todos os valores vazios/zero.

    É o formato do bug do shodan: `{"matches": [], "total": 0}` fabricado no except
    para o resto do pipeline achar que a consulta foi bem-sucedida.
    """
    if not isinstance(no, ast.Dict) or not no.keys:
        return False
    return all(_vazio(v) for v in no.values)


def _retorno_vazio(no: ast.AST | None) -> str | None:
    """Descreve o vazio devolvido, ou None quando o retorno carrega resultado real.

    Cobre as duas formas: o literal direto (`return []`) e o construtor com literal
    vazio dentro (`return RawResults(payload={})`), que era como o padrão escapava —
    todo `fetch_results` devolve um `RawResults`, então o vazio nunca aparece nu.
    """
    if no is None:
        return "devolve vazio"
    if _dict_de_sucesso_falso(no):
        return "fabrica sucesso falso"
    if _vazio(no):
        return "devolve vazio"
    if isinstance(no, ast.Call):
        args = list(no.args) + [kw.value for kw in no.keywords]
        for a in args:
            if _dict_de_sucesso_falso(a):
                return "fabrica sucesso falso"
            if _vazio(a) and not isinstance(a, ast.Constant):
                return "devolve resultado vazio embrulhado"
    return None


def _tem_raise(corpo: list[ast.stmt]) -> bool:
    return any(isinstance(n, ast.Raise) for stmt in corpo for n in ast.walk(stmt))


def _registra_lacuna(corpo: list[ast.stmt]) -> bool:
    """O except alimenta `coverage_gaps`/`errors`/contador de descarte?"""
    for stmt in corpo:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Attribute) and n.attr in ("append", "extend"):
                return True
            if isinstance(n, ast.AugAssign):  # `ruins += 1` no read_jsonl
                return True
    return False


def _funcoes_do_ciclo(arvore: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Funções do ciclo de vida, incluindo closures declaradas dentro delas."""
    achadas: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef):
            if no.name in CICLO_DE_VIDA and no.name not in ISENTAS:
                achadas.append(no)
    return achadas


def _checar_excepts(caminho: Path, fonte: str, arvore: ast.AST) -> list[str]:
    linhas = fonte.splitlines()
    problemas: list[str] = []
    for fn in _funcoes_do_ciclo(arvore):
        for no in ast.walk(fn):
            if not isinstance(no, ast.ExceptHandler):
                continue
            linha = linhas[no.lineno - 1] if no.lineno <= len(linhas) else ""
            if MARCA_ESCAPE in linha:
                continue
            if _tem_raise(no.body) or _registra_lacuna(no.body):
                continue
            for stmt in no.body:
                alvo_ruim = None
                if isinstance(stmt, ast.Return):
                    alvo_ruim = _retorno_vazio(stmt.value)
                elif isinstance(stmt, ast.Assign) and (
                    _vazio(stmt.value) or _dict_de_sucesso_falso(stmt.value)
                ):
                    alvo_ruim = (
                        "fabrica sucesso falso"
                        if _dict_de_sucesso_falso(stmt.value)
                        else "atribui vazio"
                    )
                elif isinstance(stmt, ast.Continue | ast.Pass):
                    alvo_ruim = "segue calado"
                if alvo_ruim:
                    problemas.append(
                        f"{caminho.relative_to(RAIZ)}:{stmt.lineno}: `except` em "
                        f"`{fn.name}()` {alvo_ruim} — zero achados aqui vira 'alvo limpo'. "
                        "Levante `ScanIntegrityError` ou registre em `coverage_gaps` "
                        f"(ou justifique com `# {MARCA_ESCAPE}: motivo`)."
                    )
                    break
    return problemas


def _checar_poll(caminho: Path, arvore: ast.AST) -> list[str]:
    problemas: list[str] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.AsyncFunctionDef | ast.FunctionDef) or no.name != "poll":
            continue
        trecho = ast.dump(no)
        if "attr='done'" in trecho and "attr='result'" not in trecho:
            problemas.append(
                f"{caminho.relative_to(RAIZ)}:{no.lineno}: `poll()` decide por "
                "`task.done()` sem ler `task.result()` — 'o processo terminou' não é "
                "'o processo deu certo'. Um clone que falha fecharia o scan como DONE."
            )
    return problemas


def _persistencia_grava_cobertura() -> list[str]:
    """`_persist_findings` tem que gravar a cobertura, não só o estado e as findings.

    Este é o achado que motivou estender o gate: o pipeline montava
    `scanners_skipped` corretamente e a persistência escrevia só `state=DONE`. Um
    scan em que NENHUM scanner rodou chegava à API como `state: done, errors: [],
    coverage_complete: true` — indistinguível de alvo limpo. Nenhuma regra de
    `except` pegaria isso: o defeito é uma atribuição que não existe.
    """
    fonte = (RAIZ / "orchestrator" / "jobs" / "pipelines.py").read_text(encoding="utf-8")
    trecho = fonte.split("async def _persist_findings", 1)
    if len(trecho) < 2:
        return ["orchestrator/jobs/pipelines.py: não achei `_persist_findings`"]
    corpo = trecho[1].split("\nasync def ", 1)[0]
    faltando = [
        campo
        for campo in ("scanners_skipped", "scanners_ran", "errors", "report_path")
        for _ in [None]
        if f".{campo} =" not in corpo
    ]
    if faltando:
        return [
            "orchestrator/jobs/pipelines.py: `_persist_findings` não grava "
            + ", ".join(faltando)
            + " na linha do scan — a cobertura fica calculada e nunca chega à API, "
            "à tela nem ao Fix Bundle. Foi exatamente assim que o conserto do "
            "silêncio ficou inerte ponta a ponta."
        ]
    return []


def main() -> int:
    problemas: list[str] = []
    arquivos = sorted(DIR_ADAPTERS.glob("*.py"))
    for d in DIRS_EXTRA:
        arquivos += sorted(d.glob("*.py"))
    for caminho in arquivos:
        fonte = caminho.read_text(encoding="utf-8")
        arvore = ast.parse(fonte, filename=str(caminho))
        problemas += _checar_excepts(caminho, fonte, arvore)
        problemas += _checar_poll(caminho, arvore)
    problemas += _persistencia_grava_cobertura()

    if problemas:
        print("contrato do silêncio VIOLADO:\n")
        for p in problemas:
            print(f"  ✗ {p}")
        print(
            "\nA pergunta é sempre: zero achados aqui significa LIMPO, ou significa "
            "NÃO RODOU? Se não dá para distinguir, falta um sinal.\n"
            "Ver docs/architecture.md § O contrato do silêncio."
        )
        return 1

    print(
        f"contrato do silêncio: {len(arquivos)} arquivos (adapters + pipeline + "
        "exporters), nenhum zero silencioso; a persistência grava a cobertura."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
