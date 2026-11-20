#!/usr/bin/env python3
"""Régua de efetividade do RoqueShield.

    python scripts/regua.py deteccao [--gabarito NOME] [--alvo URL] [--exigir-scanners]
                                     [--atualizar] [--saida DIR]
    python scripts/regua.py benchmark --nome python|java [--dir DIR] [--com-ia [--amostra N]]
                                      [--atualizar]
    python scripts/regua.py mutacao  [--so ID ...] [--postgres]

`deteccao` roda o `run_scan` de verdade contra um gabarito e compara os achados com ele:
`repo_sintetico` (padrão) monta o repositório de tests/regua/repo_sintetico + segredos
gerados na hora; `alvo_web` escaneia uma URL de laboratório no ar (`--alvo`, a app de
tests/regua/alvo_web/app.py). Confere a linha de base
(tests/regua/linha_de_base.json). Sai com 1 se o recall de alguma camada cair, se os
falsos positivos subirem, ou (com --exigir-scanners, o modo do CI) se alguma camada
ficar sem medir.

`benchmark` mede o SAST contra o OWASP Benchmark (Python ou Java), o gabarito que não
fomos nós que escrevemos: baixa o commit pinado, roda o semgrep do pipeline sobre os
casos e pontua por categoria como o scorecard oficial (acerto menos falso positivo).
Com `--com-ia`, uma amostra fixa dos achados (metade em casos reais, metade em
armadilhas) passa pela triagem do modelo configurado, e a régua mede se ele descarta o
falso positivo sem descartar o real. Sem modelo configurado, a triagem sai NÃO MEDIDA.

`mutacao` aplica cada mutação do catálogo (tests/regua/mutacoes.yaml): desfaz um
controle crítico, roda o teste que diz protegê-lo e exige que ele reprove. Sai com 1 se
algum controle puder ser removido sem nenhum teste notar, ou se o trecho do catálogo não
existir mais no código (catálogo velho também é régua quebrada).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import shutil
import string
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
REGUA = RAIZ / "tests" / "regua"
FIXTURE = REGUA / "repo_sintetico"
GABARITOS = REGUA / "gabaritos"
LINHA_DE_BASE = REGUA / "linha_de_base.json"
CATALOGO = REGUA / "mutacoes.yaml"


# ============================================================ segredos de teste


def _segredos_de_teste() -> dict[str, str]:
    """Credenciais FALSAS, com o formato que os detectores reconhecem.

    Valores fixos (semente fixa) para a medição ser reprodutível. Os prefixos são
    montados por concatenação: o literal nunca aparece neste arquivo, que o gitleaks
    do próprio repositório varre.
    """
    r = random.Random(20261119)  # noqa: S311 - não é cripto, é fixture reprodutível
    b32 = string.ascii_uppercase + "234567"
    alnum = string.ascii_letters + string.digits

    def pega(alfabeto: str, n: int) -> str:
        return "".join(r.choice(alfabeto) for _ in range(n))

    aws_id = "AK" + "IA" + pega(b32, 16)
    aws_secret = pega(alnum + "/+", 40)
    gh = "gh" + "p_" + pega(alnum, 36)
    slack = (
        "xo"
        + "xb-"
        + pega(string.digits, 12)
        + "-"
        + pega(string.digits, 12)
        + "-"
        + pega(alnum, 24)
    )
    corpo = "\n".join(pega(alnum + "+/", 64) for _ in range(12))
    marca = "-----BEGIN RSA " + "PRIVATE KEY-----"
    fim = "-----END RSA " + "PRIVATE KEY-----"
    return {
        "segredos/aws_credentials.ini": (
            f"[default]\naws_access_key_id = {aws_id}\naws_secret_access_key = {aws_secret}\n"
        ),
        "segredos/github_token.txt": f"GITHUB_TOKEN={gh}\n",
        "segredos/deploy_key.pem": f"{marca}\n{corpo}\n{fim}\n",
        "segredos/slack_bot.txt": f"SLACK_BOT_TOKEN={slack}\n",
    }


def desembrulhar(destino: Path) -> None:
    """Tira o sufixo `.regua` dos manifestos de dependência do fixture.

    Eles ficam no repositório com o sufixo porque este repo é PÚBLICO e o grafo de
    dependências do GitHub lê `package-lock.json`, `pom.xml`, `go.mod` em qualquer pasta:
    o Log4Shell e o lodash plantados de propósito virariam alerta crítico na página do
    projeto. O Trivy precisa do nome de verdade, então a régua renomeia ao montar.
    """
    for f in sorted(destino.rglob("*.regua")):
        f.rename(f.with_name(f.name.removesuffix(".regua")))


def montar_repo(destino: Path) -> Path:
    """Copia o fixture, gera os segredos e faz UM commit: o gitleaks clona e varre o
    histórico, então um `git init` vazio mediria zero e pareceria limpo."""
    shutil.copytree(FIXTURE, destino)
    desembrulhar(destino)
    for rel, conteudo in _segredos_de_teste().items():
        alvo = destino / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(conteudo, encoding="utf-8")
    git = [
        "git",
        "-c",
        "user.name=regua",
        "-c",
        "user.email=regua@roqueshield.test",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run([*git, "init", "-q", str(destino)], check=True)
    subprocess.run([*git, "-C", str(destino), "add", "-A"], check=True)
    subprocess.run([*git, "-C", str(destino), "commit", "-q", "-m", "gabarito"], check=True)
    return destino


# ============================================================ métricas


def _gravar_metricas(arquivo: str | None, linhas: list[str]) -> None:
    """Acrescenta linhas no formato do coletor textfile do node-exporter (régua noturna
    da produção). A régua noturna junta os arquivos de cada etapa num só."""
    if not arquivo:
        return
    with open(arquivo, "a", encoding="utf-8") as fh:
        fh.write("\n".join(linhas) + "\n")


def _m(nome: str, valor: float, **rotulos: str) -> str:
    r = ",".join(f'{k}="{v}"' for k, v in rotulos.items())
    return f"roqueshield_{nome}{{{r}}} {valor}"


# ============================================================ detecção


async def _medir(gabarito: Any, alvo: str) -> Any:
    import orchestrator.persistence.models  # noqa: F401 - registra as tabelas no metadata
    from orchestrator.domain.schemas import AssetType, Target
    from orchestrator.jobs.pipelines import run_scan
    from orchestrator.persistence.db import init_db
    from orchestrator.regua.placar import avaliar

    await init_db()
    scanners = sorted({s for c in gabarito.camadas.values() for s in c.scanners})
    tipo = {"repo": AssetType.REPO, "url": AssetType.URL, "imagem": AssetType.IMAGE}[
        gabarito.alvo.tipo
    ]
    t0 = time.monotonic()
    r = await run_scan(
        Target(asset_type=tipo, value=alvo),
        skip_ai=True,
        scanners=scanners,
        options=gabarito.alvo.opcoes or None,
    )
    placar = avaliar(
        gabarito,
        r.findings,
        scanners_ran=r.scanners_ran,
        scanners_skipped=r.scanners_skipped,
        raiz=alvo if gabarito.alvo.tipo == "repo" else None,
    )
    return placar, time.monotonic() - t0, len(r.findings)


def deteccao(args: argparse.Namespace) -> int:
    from orchestrator.regua.placar import (
        Gabarito,
        comparar_com_linha_de_base,
        markdown,
        nova_linha_de_base,
        salvar,
    )

    gabarito = Gabarito.carregar(GABARITOS / f"{args.gabarito}.yaml")
    if gabarito.alvo.tipo in ("url", "imagem"):
        alvo = args.alvo or gabarito.alvo.valor
        if not alvo:
            print(f"o gabarito {gabarito.nome} escaneia um alvo no ar: passe --alvo")
            return 2
        placar, segundos, total = asyncio.run(_medir(gabarito, alvo))
    else:
        with tempfile.TemporaryDirectory(prefix="regua-") as tmp:
            repo = montar_repo(Path(tmp) / "repo")
            placar, segundos, total = asyncio.run(_medir(gabarito, str(repo)))

    print(markdown(placar))
    print(
        f"_{total} achados em {segundos:.0f}s; rodaram {placar.scanners_rodaram}; "
        f"pulados {list(placar.scanners_pulados) or 'nenhum'}_\n"
    )
    if args.saida:
        salvar(placar, Path(args.saida))
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as fh:
            fh.write(markdown(placar))

    linha = json.loads(LINHA_DE_BASE.read_text(encoding="utf-8")) if LINHA_DE_BASE.exists() else {}
    if args.atualizar:
        nova, recusas = nova_linha_de_base(placar, linha)
        LINHA_DE_BASE.write_text(
            json.dumps(nova, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for r in recusas:
            print(f"  linha de base: {r}")
        print(f"linha de base gravada em {LINHA_DE_BASE.relative_to(RAIZ)}")
        return 0
    problemas = comparar_com_linha_de_base(placar, linha, exigir_medida=args.exigir_scanners)
    metricas: list[str] = []
    for c in placar.camadas.values():
        rot = {"gabarito": placar.gabarito, "camada": c.camada}
        metricas.append(_m("regua_medida", 1 if c.medida else 0, **rot))
        if c.recall is not None:
            metricas.append(_m("regua_recall", c.recall, **rot))
        metricas.append(_m("regua_falsos_positivos", c.falsos_positivos, **rot))
        if c.classificacao is not None:
            metricas.append(_m("regua_classificacao", c.classificacao, **rot))
    metricas.append(_m("regua_problemas", len(problemas), gabarito=placar.gabarito))
    _gravar_metricas(args.metricas, metricas)
    nao_medidas = [c for c in placar.camadas.values() if not c.medida]
    for c in nao_medidas:
        if not args.exigir_scanners:
            print(
                f"AVISO: camada '{c.camada}' NÃO MEDIDA ({c.motivo_nao_medida}). "
                "Isto não é verde: instale o scanner ou rode no CI."
            )
    if problemas:
        print("RÉGUA REPROVOU:")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print("régua de detecção: nenhuma regressão contra a linha de base.")
    return 0


# ============================================================ OWASP Benchmark

# Commit pinado de cada Benchmark (GPL: baixado na hora, nunca copiado para cá), o
# gabarito e a pasta dos casos dentro dele.
BENCHMARKS: dict[str, dict[str, str]] = {
    "python": {
        "repo": "https://github.com/OWASP-Benchmark/BenchmarkPython.git",
        "commit": "f1291485808b66e20ddb6b01b10dc71b3df8c8ba",
        "gabarito": "expectedresults-0.1.csv",
        "casos": "testcode",
    },
    "java": {
        "repo": "https://github.com/OWASP-Benchmark/BenchmarkJava.git",
        "commit": "10dfcc54ad02dcfcb358b0ba4a0fef8c919a6d17",
        "gabarito": "expectedresults-1.2.csv",
        "casos": "src/main/java/org/owasp/benchmark/testcode",
    },
}


def _baixar_benchmark(nome: str, destino: Path) -> Path:
    b = BENCHMARKS[nome]
    subprocess.run(["git", "init", "-q", str(destino)], check=True)
    subprocess.run(["git", "-C", str(destino), "remote", "add", "origin", b["repo"]], check=True)
    subprocess.run(
        ["git", "-C", str(destino), "fetch", "-q", "--depth", "1", "origin", b["commit"]],
        check=True,
    )
    subprocess.run(["git", "-C", str(destino), "checkout", "-q", "FETCH_HEAD"], check=True)
    return destino


async def _scan_benchmark(casos: Path) -> Any:
    import orchestrator.persistence.models  # noqa: F401 - registra as tabelas no metadata
    from orchestrator.domain.schemas import AssetType, Target
    from orchestrator.jobs.pipelines import run_scan
    from orchestrator.persistence.db import init_db

    await init_db()
    return await run_scan(
        Target(asset_type=AssetType.REPO, value=str(casos)), skip_ai=True, scanners=["semgrep"]
    )


def benchmark(args: argparse.Namespace) -> int:
    from orchestrator.regua.benchmark import (
        avaliar_benchmark,
        comparar_benchmark,
        ler_gabarito,
        linha_de_base_benchmark,
        markdown_benchmark,
    )

    b = BENCHMARKS[args.nome]
    with tempfile.TemporaryDirectory(prefix="benchmark-") as tmp:
        raiz = Path(args.dir) if args.dir else _baixar_benchmark(args.nome, Path(tmp) / "b")
        casos = ler_gabarito(raiz / b["gabarito"])
        t0 = time.monotonic()
        r = asyncio.run(_scan_benchmark(raiz / b["casos"]))
        segundos = time.monotonic() - t0
    if "semgrep" not in r.scanners_ran:
        print(f"BENCHMARK NÃO MEDIDO: o semgrep não rodou ({r.scanners_skipped}).")
        return 1
    placar = avaliar_benchmark(args.nome, casos, r.findings)
    texto = markdown_benchmark(placar) + f"\n_{len(r.findings)} achados em {segundos:.0f}s_\n"
    print(texto)
    if args.saida:
        destino = Path(args.saida)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / f"benchmark-{args.nome}.json").write_text(
            placar.model_dump_json(indent=2), encoding="utf-8"
        )
        (destino / f"benchmark-{args.nome}.md").write_text(texto, encoding="utf-8")
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as fh:
            fh.write(texto)
    linha = json.loads(LINHA_DE_BASE.read_text(encoding="utf-8")) if LINHA_DE_BASE.exists() else {}
    chave = f"benchmark_{args.nome}"
    if args.atualizar and args.com_ia:
        return _gravar_triagem(args, casos, r.findings, linha)
    if args.atualizar:
        antes = linha.get(chave)
        nova = linha_de_base_benchmark(placar)
        if antes and comparar_benchmark(placar, antes):
            print("linha de base: o placar piorou; a catraca não grava piora automaticamente")
            return 1
        linha[chave] = nova
        LINHA_DE_BASE.write_text(
            json.dumps(linha, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"linha de base do benchmark gravada: {nova}")
        return 0
    problemas = comparar_benchmark(placar, linha.get(chave))
    metricas = [
        _m("benchmark_nota", round(placar.nota_media, 4), benchmark=args.nome),
        _m("benchmark_acerto", round(placar.tpr_medio, 4), benchmark=args.nome),
        _m("benchmark_falso_positivo", round(placar.fpr_medio, 4), benchmark=args.nome),
    ]
    metricas += [
        _m("benchmark_nota_categoria", round(c.nota, 4), benchmark=args.nome, categoria=c.categoria)
        for c in placar.categorias.values()
    ]
    _gravar_metricas(getattr(args, "metricas", None), metricas)
    if args.com_ia:
        problemas += _medir_triagem(args, casos, r.findings, linha)
    if problemas:
        print("BENCHMARK REPROVOU:")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print("benchmark: nenhuma regressão contra a linha de base.")
    return 0


def _triar(args: argparse.Namespace, casos: Any, findings: list[Any]) -> Any:
    from orchestrator.ai.analyzer import triage_batch
    from orchestrator.regua.benchmark import amostra_estratificada, avaliar_triagem

    amostra = [
        f.model_copy(deep=True) for f in amostra_estratificada(casos, findings, args.amostra)
    ]
    asyncio.run(triage_batch(amostra, skip_severities=set()))
    return avaliar_triagem(casos, amostra)


def _medir_triagem(
    args: argparse.Namespace, casos: Any, findings: list[Any], linha: dict[str, Any]
) -> list[str]:
    from orchestrator.regua.benchmark import comparar_triagem, markdown_triagem

    placar = _triar(args, casos, findings)
    texto = markdown_triagem(placar, args.nome)
    print(texto)
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as fh:
            fh.write(texto)
    if args.saida:
        (Path(args.saida) / f"triagem-{args.nome}.json").write_text(
            placar.model_dump_json(indent=2), encoding="utf-8"
        )
    rot = {"benchmark": args.nome}
    metricas = [_m("triagem_ia_medida", 1 if placar.medida else 0, **rot)]
    if placar.medida:
        metricas += [
            _m("triagem_ia_nota", round(placar.nota or 0.0, 4), **rot),
            _m("triagem_ia_descarte_certo", round(placar.descarte_certo or 0.0, 4), **rot),
            _m("triagem_ia_descarte_errado", round(placar.descarte_errado or 0.0, 4), **rot),
        ]
    _gravar_metricas(args.metricas, metricas)
    return comparar_triagem(placar, linha.get(f"triagem_ia_{args.nome}"))


def _gravar_triagem(
    args: argparse.Namespace, casos: Any, findings: list[Any], linha: dict[str, Any]
) -> int:
    from orchestrator.regua.benchmark import comparar_triagem, markdown_triagem

    placar = _triar(args, casos, findings)
    print(markdown_triagem(placar, args.nome))
    if not placar.medida:
        print("triagem não medida: linha de base mantida")
        return 1
    chave = f"triagem_ia_{args.nome}"
    if linha.get(chave) and comparar_triagem(placar, linha[chave]):
        print("linha de base: a triagem piorou; a catraca não grava piora automaticamente")
        return 1
    linha[chave] = {
        "nota_min": round(placar.nota or 0.0, 4),
        "descarte_errado_max": round(placar.descarte_errado or 0.0, 4),
    }
    LINHA_DE_BASE.write_text(
        json.dumps(linha, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"linha de base da triagem gravada: {linha[chave]}")
    return 0


# ============================================================ mutação


def mutacao(args: argparse.Namespace) -> int:
    import yaml

    catalogo = yaml.safe_load(CATALOGO.read_text(encoding="utf-8"))["mutacoes"]
    if args.so:
        catalogo = [m for m in catalogo if m["id"] in set(args.so)]
    tem_pg = bool(os.environ.get("ROQUESHIELD_PG_TEST_URL"))
    resultados: list[tuple[str, str, str]] = []
    for m in catalogo:
        if m.get("requer") == "postgres" and not (args.postgres and tem_pg):
            resultados.append(
                (m["id"], "NÃO MEDIDA", "exige Postgres (--postgres + ROQUESHIELD_PG_TEST_URL)")
            )
            continue
        arquivo = RAIZ / m["arquivo"]
        original = arquivo.read_text(encoding="utf-8")
        # `trocas`: quando o controle tem duas camadas (checagem antecipada + condição
        # atômica no UPDATE), desfazer uma só é mutante equivalente: a outra segura.
        trocas = m.get("trocas") or [{"de": m["de"], "para": m["para"]}]
        faltando = [t["de"] for t in trocas if original.count(t["de"]) != 1]
        if faltando:
            resultados.append(
                (m["id"], "CATÁLOGO VELHO", f"trecho ausente ou ambíguo em {m['arquivo']}")
            )
            continue
        mutado = original
        for t in trocas:
            mutado = mutado.replace(t["de"], t["para"], 1)
        arquivo.write_text(mutado, encoding="utf-8")
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "-x",
                    *m["teste"].split(),
                ],
                cwd=RAIZ,
                capture_output=True,
                text=True,
                check=False,
            )
            pegou = r.returncode != 0 and (" failed" in r.stdout or " error" in r.stdout)
            resultados.append((m["id"], "PEGA" if pegou else "ESCAPOU", m["controle"]))
        finally:
            arquivo.write_text(original, encoding="utf-8")

    medidas = [x for x in resultados if x[1] in ("PEGA", "ESCAPOU")]
    pegas = sum(1 for x in medidas if x[1] == "PEGA")
    linhas = [
        "## Régua dos testes (mutação dos controles críticos)",
        "",
        "| Mutação | Resultado | Controle |",
        "| --- | --- | --- |",
    ]
    linhas += [f"| `{i}` | {res} | {ctl} |" for i, res, ctl in resultados]
    linhas += [
        "",
        f"**Placar: {pegas}/{len(medidas)} mutações pegas**"
        + (
            f" ({len(resultados) - len(medidas)} não medidas)"
            if len(medidas) < len(resultados)
            else ""
        ),
    ]
    texto = "\n".join(linhas) + "\n"
    print(texto)
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as fh:
            fh.write(texto)
    quebradas = [x for x in resultados if x[1] in ("ESCAPOU", "CATÁLOGO VELHO")]
    if quebradas:
        print("RÉGUA DOS TESTES REPROVOU: " + ", ".join(f"{i} ({res})" for i, res, _ in quebradas))
        return 1
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("deteccao", help="recall e falsos positivos contra o gabarito")
    d.add_argument("--gabarito", default="repo_sintetico", help="tests/regua/gabaritos/<nome>.yaml")
    d.add_argument("--alvo", help="URL de laboratório, para gabarito de alvo web")
    d.add_argument("--exigir-scanners", action="store_true", help="camada sem medir reprova (CI)")
    d.add_argument(
        "--atualizar", action="store_true", help="grava o placar como linha de base (só sobe)"
    )
    d.add_argument("--saida", help="pasta para o placar em JSON e Markdown")
    d.add_argument("--metricas", help="acrescenta as métricas (formato Prometheus) neste arquivo")
    bm = sub.add_parser("benchmark", help="SAST contra o OWASP Benchmark (Python ou Java)")
    bm.add_argument("--nome", choices=sorted(BENCHMARKS), required=True)
    bm.add_argument("--dir", help="checkout já baixado do Benchmark (senão baixa o pin)")
    bm.add_argument("--atualizar", action="store_true", help="grava a nota como linha de base")
    bm.add_argument("--saida", help="pasta para o placar em JSON e Markdown")
    bm.add_argument("--com-ia", action="store_true", help="mede também a triagem do modelo")
    bm.add_argument("--metricas", help="acrescenta as métricas (formato Prometheus) neste arquivo")
    bm.add_argument("--amostra", type=int, default=120, help="achados triados (metade reais)")
    m = sub.add_parser("mutacao", help="desfaz cada controle crítico e exige que um teste reprove")
    m.add_argument("--so", nargs="*", help="só estas mutações (ids)")
    m.add_argument("--postgres", action="store_true", help="inclui as mutações que exigem Postgres")
    args = p.parse_args()
    if args.cmd in ("deteccao", "benchmark"):
        # Banco e pastas isolados: a régua não toca o SQLite de desenvolvimento.
        tmp = Path(tempfile.mkdtemp(prefix="regua-dados-"))
        os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{tmp / 'regua.db'}")
        os.environ.setdefault("DATA_DIR", str(tmp / "data"))
        os.environ.setdefault("REPORTS_DIR", str(tmp / "reports"))
        os.environ.setdefault("LITELLM_MODE", "PRODUCTION")
        return deteccao(args) if args.cmd == "deteccao" else benchmark(args)
    return mutacao(args)


if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ))
    sys.exit(main())
