#!/usr/bin/env python3
"""Régua de efetividade do RoqueShield.

    python scripts/regua.py deteccao [--exigir-scanners] [--atualizar] [--saida DIR]
    python scripts/regua.py mutacao  [--so ID ...] [--postgres]

`deteccao` monta o repositório sintético (tests/regua/repo_sintetico + segredos gerados
na hora), roda o `run_scan` de verdade, compara os achados com o gabarito
(tests/regua/gabaritos/repo_sintetico.yaml) e confere a linha de base
(tests/regua/linha_de_base.json). Sai com 1 se o recall de alguma camada cair, se os
falsos positivos subirem, ou (com --exigir-scanners, o modo do CI) se alguma camada
ficar sem medir.

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
GABARITO = REGUA / "gabaritos" / "repo_sintetico.yaml"
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


def montar_repo(destino: Path) -> Path:
    """Copia o fixture, gera os segredos e faz UM commit: o gitleaks clona e varre o
    histórico, então um `git init` vazio mediria zero e pareceria limpo."""
    shutil.copytree(FIXTURE, destino)
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


# ============================================================ detecção


async def _medir(repo: Path) -> Any:
    import orchestrator.persistence.models  # noqa: F401 - registra as tabelas no metadata
    from orchestrator.domain.schemas import AssetType, Target
    from orchestrator.jobs.pipelines import run_scan
    from orchestrator.persistence.db import init_db
    from orchestrator.regua.placar import Gabarito, avaliar

    await init_db()
    gabarito = Gabarito.carregar(GABARITO)
    scanners = sorted({s for c in gabarito.camadas.values() for s in c.scanners})
    t0 = time.monotonic()
    r = await run_scan(
        Target(asset_type=AssetType.REPO, value=str(repo)), skip_ai=True, scanners=scanners
    )
    placar = avaliar(
        gabarito,
        r.findings,
        scanners_ran=r.scanners_ran,
        scanners_skipped=r.scanners_skipped,
        raiz=str(repo),
    )
    return placar, time.monotonic() - t0, len(r.findings)


def deteccao(args: argparse.Namespace) -> int:
    from orchestrator.regua.placar import (
        comparar_com_linha_de_base,
        markdown,
        nova_linha_de_base,
        salvar,
    )

    with tempfile.TemporaryDirectory(prefix="regua-") as tmp:
        repo = montar_repo(Path(tmp) / "repo")
        placar, segundos, total = asyncio.run(_medir(repo))

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
    d.add_argument("--exigir-scanners", action="store_true", help="camada sem medir reprova (CI)")
    d.add_argument(
        "--atualizar", action="store_true", help="grava o placar como linha de base (só sobe)"
    )
    d.add_argument("--saida", help="pasta para o placar em JSON e Markdown")
    m = sub.add_parser("mutacao", help="desfaz cada controle crítico e exige que um teste reprove")
    m.add_argument("--so", nargs="*", help="só estas mutações (ids)")
    m.add_argument("--postgres", action="store_true", help="inclui as mutações que exigem Postgres")
    args = p.parse_args()
    if args.cmd == "deteccao":
        # Banco e pastas isolados: a régua não toca o SQLite de desenvolvimento.
        tmp = Path(tempfile.mkdtemp(prefix="regua-dados-"))
        os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{tmp / 'regua.db'}")
        os.environ.setdefault("DATA_DIR", str(tmp / "data"))
        os.environ.setdefault("REPORTS_DIR", str(tmp / "reports"))
        os.environ.setdefault("LITELLM_MODE", "PRODUCTION")
        return deteccao(args)
    return mutacao(args)


if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ))
    sys.exit(main())
