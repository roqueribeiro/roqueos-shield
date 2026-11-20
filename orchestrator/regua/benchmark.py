"""Placar contra o OWASP Benchmark: a medida que NÃO fomos nós que escrevemos.

O gabarito sintético da régua (tests/regua/) prova que a ferramenta acha o que plantamos,
e o ruleset foi ajustado olhando para ele. O OWASP Benchmark é de terceiros: milhares de
casos pequenos, metade vulnerável e metade armadilha (o mesmo código com o dado
sanitizado ou o caminho morto), com o gabarito publicado em `expectedresults-*.csv`.

A pontuação é a do próprio Benchmark, por categoria:

    acerto (TPR)        = verdadeiros positivos / casos vulneráveis
    falso positivo (FPR) = falsos positivos / casos não vulneráveis
    nota                = TPR - FPR       (índice de Youden; 0 = chutar, 1 = perfeito)

Uma ferramenta que marcasse tudo teria TPR 1 e FPR 1: nota zero. É isso que impede o
placar de premiar barulho.

Um caso conta como "apontado" quando algum achado NO ARQUIVO dele traz uma CWE da
categoria. As CWEs equivalentes ficam em `CWES_DA_CATEGORIA`: o Benchmark escreve uma
CWE por categoria (hash = 328), e as ferramentas usam as vizinhas (327, 916).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from pydantic import BaseModel, Field

from orchestrator.domain.schemas import Finding

# Categoria do Benchmark -> CWEs que contam como acerto para ela.
CWES_DA_CATEGORIA: dict[str, set[str]] = {
    "cmdi": {"CWE-78", "CWE-77"},
    "codeinj": {"CWE-94", "CWE-95"},
    "crypto": {"CWE-327", "CWE-326"},
    "deserialization": {"CWE-502"},
    "hash": {"CWE-328", "CWE-327", "CWE-916"},
    "ldapi": {"CWE-90"},
    "pathtraver": {"CWE-22", "CWE-23", "CWE-36", "CWE-73"},
    "redirect": {"CWE-601"},
    "securecookie": {"CWE-614", "CWE-1004"},
    "sqli": {"CWE-89"},
    "trustbound": {"CWE-501"},
    "weakrand": {"CWE-330", "CWE-338"},
    "xpathi": {"CWE-643"},
    "xss": {"CWE-79", "CWE-80"},
    "xxe": {"CWE-611"},
}

_CASO = re.compile(r"(BenchmarkTest\d{5})")
# A linha de base guarda 4 casas; o valor de hoje tem todas. Sem a folga, +24,365%
# medido contra +24,37% gravado reprovava a régua por arredondamento (aconteceu).
_TOL = 1e-4


class Caso(BaseModel):
    nome: str
    categoria: str
    vulneravel: bool
    cwe: str


class PlacarCategoria(BaseModel):
    categoria: str
    vulneraveis: int
    armadilhas: int
    verdadeiros_positivos: int
    falsos_positivos: int
    tpr: float
    fpr: float
    nota: float


class PlacarBenchmark(BaseModel):
    nome: str
    casos: int
    categorias: dict[str, PlacarCategoria]
    nota_media: float  # média das notas por categoria, como o scorecard oficial
    tpr_medio: float
    fpr_medio: float
    sem_regra: list[str] = Field(default_factory=list)  # categorias com TPR zero


def ler_gabarito(csv_path: Path) -> list[Caso]:
    casos: list[Caso] = []
    with csv_path.open(encoding="utf-8") as fh:
        for linha in csv.reader(fh):
            if not linha or linha[0].lstrip().startswith("#"):
                continue
            nome, categoria, vulneravel, cwe = (c.strip() for c in linha[:4])
            casos.append(
                Caso(
                    nome=nome,
                    categoria=categoria,
                    vulneravel=vulneravel.lower() == "true",
                    cwe=f"CWE-{cwe}",
                )
            )
    if not casos:
        raise ValueError(f"{csv_path}: gabarito vazio, nada para medir")
    return casos


def _cwes_por_caso(findings: list[Finding]) -> dict[str, set[str]]:
    por_caso: dict[str, set[str]] = {}
    for f in findings:
        m = _CASO.search(f.target.value)
        if m:
            por_caso.setdefault(m.group(1), set()).update(f.cwe)
    return por_caso


def avaliar_benchmark(nome: str, casos: list[Caso], findings: list[Finding]) -> PlacarBenchmark:
    por_caso = _cwes_por_caso(findings)
    categorias: dict[str, PlacarCategoria] = {}
    for cat in sorted({c.categoria for c in casos}):
        aceitas = CWES_DA_CATEGORIA.get(cat, set()) | {c.cwe for c in casos if c.categoria == cat}
        tp = fp = vuln = arm = 0
        for c in casos:
            if c.categoria != cat:
                continue
            apontado = bool(por_caso.get(c.nome, set()) & aceitas)
            if c.vulneravel:
                vuln += 1
                tp += apontado
            else:
                arm += 1
                fp += apontado
        tpr = tp / vuln if vuln else 0.0
        fpr = fp / arm if arm else 0.0
        categorias[cat] = PlacarCategoria(
            categoria=cat,
            vulneraveis=vuln,
            armadilhas=arm,
            verdadeiros_positivos=tp,
            falsos_positivos=fp,
            tpr=tpr,
            fpr=fpr,
            nota=tpr - fpr,
        )
    n = len(categorias)
    return PlacarBenchmark(
        nome=nome,
        casos=len(casos),
        categorias=categorias,
        nota_media=sum(c.nota for c in categorias.values()) / n,
        tpr_medio=sum(c.tpr for c in categorias.values()) / n,
        fpr_medio=sum(c.fpr for c in categorias.values()) / n,
        sem_regra=[c.categoria for c in categorias.values() if c.tpr == 0],
    )


def markdown_benchmark(p: PlacarBenchmark) -> str:
    linhas = [
        f"## OWASP Benchmark ({p.nome}): {p.casos} casos",
        "",
        f"**Nota média {p.nota_media:+.0%}** (acerto {p.tpr_medio:.0%}, "
        f"falso positivo {p.fpr_medio:.0%}). Nota = acerto - falso positivo; 0 é chutar.",
        "",
        "| Categoria | Acerto (TPR) | Falso positivo (FPR) | Nota | Vulneráveis | Armadilhas |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for c in p.categorias.values():
        linhas.append(
            f"| {c.categoria} | {c.tpr:.0%} ({c.verdadeiros_positivos}/{c.vulneraveis}) | "
            f"{c.fpr:.0%} ({c.falsos_positivos}/{c.armadilhas}) | {c.nota:+.0%} | "
            f"{c.vulneraveis} | {c.armadilhas} |"
        )
    if p.sem_regra:
        linhas += ["", "**Categorias sem nenhum acerto:** " + ", ".join(p.sem_regra)]
    return "\n".join(linhas) + "\n"


def comparar_benchmark(p: PlacarBenchmark, linha: dict[str, float] | None) -> list[str]:
    """Catraca: a nota média e o acerto médio não descem; o falso positivo não sobe."""
    if not linha:
        return [f"benchmark {p.nome}: sem linha de base (registre com --atualizar)"]
    problemas: list[str] = []
    if p.nota_media + _TOL < linha["nota_min"]:
        problemas.append(
            f"benchmark {p.nome}: nota média caiu para {p.nota_media:+.1%} "
            f"(linha de base {linha['nota_min']:+.1%})"
        )
    if p.tpr_medio + _TOL < linha["tpr_min"]:
        problemas.append(
            f"benchmark {p.nome}: acerto médio caiu para {p.tpr_medio:.1%} "
            f"(linha de base {linha['tpr_min']:.1%})"
        )
    if p.fpr_medio > linha["fpr_max"] + _TOL:
        problemas.append(
            f"benchmark {p.nome}: falso positivo médio subiu para {p.fpr_medio:.1%} "
            f"(linha de base {linha['fpr_max']:.1%})"
        )
    return problemas


def linha_de_base_benchmark(p: PlacarBenchmark) -> dict[str, float]:
    return {
        "nota_min": round(p.nota_media, 4),
        "tpr_min": round(p.tpr_medio, 4),
        "fpr_max": round(p.fpr_medio, 4),
    }


# ------------------------------------------------------------ a triagem da IA


class PlacarTriagem(BaseModel):
    """A IA separa o achado real do falso positivo?

    Gabarito: o mesmo Benchmark. Achado do scanner num caso VULNERÁVEL é real; achado num
    caso ARMADILHA é falso positivo conhecido. A triagem boa descarta os segundos e
    preserva os primeiros:

        descarte certo  = armadilhas marcadas como falso positivo / achados em armadilha
        descarte errado = vulneráveis marcados como falso positivo / achados em vulnerável
        nota            = descarte certo - descarte errado

    Descartar um achado real é o erro caro (some do relatório do banco), por isso ele
    entra com o mesmo peso do acerto: uma IA que descartasse tudo tiraria zero.
    """

    medida: bool
    motivo_nao_medida: str | None = None
    modelo: str | None = None
    achados_reais: int = 0
    achados_em_armadilha: int = 0
    descartes_certos: int = 0
    descartes_errados: int = 0
    descarte_certo: float | None = None
    descarte_errado: float | None = None
    nota: float | None = None


def avaliar_triagem(casos: list[Caso], findings: list[Finding]) -> PlacarTriagem:
    from orchestrator.ai.analyzer import TRIAGEM_DETERMINISTICA

    vulneravel = {c.nome: c.vulneravel for c in casos}
    triados = [f for f in findings if f.ai_triage is not None]
    if not triados:
        return PlacarTriagem(medida=False, motivo_nao_medida="nenhum achado foi triado")
    modelos = {f.ai_triage.model_used for f in triados if f.ai_triage}
    if modelos <= {TRIAGEM_DETERMINISTICA}:
        return PlacarTriagem(
            medida=False,
            motivo_nao_medida="a triagem caiu na regra determinística (IA sem credencial "
            "ou fora do ar): nada aqui mede um modelo",
        )
    reais = arm = certos = errados = 0
    for f in triados:
        m = _CASO.search(f.target.value)
        if not m or m.group(1) not in vulneravel or f.ai_triage is None:
            continue
        descartou = f.ai_triage.is_likely_false_positive
        if vulneravel[m.group(1)]:
            reais += 1
            errados += descartou
        else:
            arm += 1
            certos += descartou
    certo = certos / arm if arm else 0.0
    errado = errados / reais if reais else 0.0
    return PlacarTriagem(
        medida=True,
        modelo=", ".join(sorted(modelos - {TRIAGEM_DETERMINISTICA})),
        achados_reais=reais,
        achados_em_armadilha=arm,
        descartes_certos=certos,
        descartes_errados=errados,
        descarte_certo=certo,
        descarte_errado=errado,
        nota=certo - errado,
    )


def amostra_estratificada(
    casos: list[Caso], findings: list[Finding], tamanho: int
) -> list[Finding]:
    """Metade de achados em casos vulneráveis, metade em armadilhas, espalhados pelas
    categorias e sempre os mesmos (ordem fixa): a nota de hoje compara com a de ontem."""
    vulneravel = {c.nome: c.vulneravel for c in casos}
    reais: list[Finding] = []
    armadilhas: list[Finding] = []
    for f in sorted(findings, key=lambda x: (x.target.value, x.source_rule_id or "")):
        m = _CASO.search(f.target.value)
        if m and m.group(1) in vulneravel:
            (reais if vulneravel[m.group(1)] else armadilhas).append(f)

    def espalhar(lista: list[Finding], n: int) -> list[Finding]:
        if len(lista) <= n:
            return lista
        passo = len(lista) / n
        return [lista[int(i * passo)] for i in range(n)]

    return espalhar(reais, tamanho // 2) + espalhar(armadilhas, tamanho - tamanho // 2)


def markdown_triagem(p: PlacarTriagem, nome: str) -> str:
    if not p.medida:
        return f"## Triagem da IA ({nome}): NÃO MEDIDA\n\n{p.motivo_nao_medida}\n"
    certo, errado, nota = p.descarte_certo or 0.0, p.descarte_errado or 0.0, p.nota or 0.0
    return (
        f"## Triagem da IA ({nome}), modelo {p.modelo}\n\n"
        f"**Nota {nota:+.0%}**: descartou {certo:.0%} dos falsos positivos "
        f"({p.descartes_certos}/{p.achados_em_armadilha}) e {errado:.0%} dos "
        f"achados reais ({p.descartes_errados}/{p.achados_reais}). Descartar achado real é "
        "o erro caro: some do relatório.\n"
    )


def comparar_triagem(p: PlacarTriagem, linha: dict[str, float] | None) -> list[str]:
    if not p.medida:
        return [f"triagem da IA: não medida ({p.motivo_nao_medida})"]
    if not linha:
        return ["triagem da IA: sem linha de base (registre com --atualizar)"]
    nota, errado = p.nota or 0.0, p.descarte_errado or 0.0
    problemas: list[str] = []
    if nota + _TOL < linha["nota_min"]:
        problemas.append(
            f"triagem da IA: nota caiu para {nota:+.1%} (linha de base {linha['nota_min']:+.1%})"
        )
    if errado > linha["descarte_errado_max"] + _TOL:
        problemas.append(
            f"triagem da IA: descartou {errado:.1%} dos achados reais "
            f"(linha de base {linha['descarte_errado_max']:.1%})"
        )
    return problemas
