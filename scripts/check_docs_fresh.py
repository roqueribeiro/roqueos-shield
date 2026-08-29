#!/usr/bin/env python3
"""Gate de documentação: reprova quando o código anda e a doc fica para trás.

Regra sem mecanismo é decoração. "Manter a doc atualizada" é um bom propósito e um
péssimo controle: ninguém percebe quando ela envelhece. Este script compara a
documentação com o CÓDIGO — não com a boa vontade de quem escreveu — e falha o CI
quando os dois discordam.

O que ele checa, e por que cada um existe:

1. **Scanners.** A lista que o README anuncia tem que ser a que a fábrica sabe
   construir. O nuclei ficou órfão por meses enquanto a UI o prometia; um scanner
   documentado e não construível é promessa falsa para quem confia na ferramenta.
2. **Variáveis de ambiente.** Toda `Settings` precisa aparecer no `.env.example`.
   Uma opção sem documentação é uma opção que ninguém liga — foi o caso de metade
   dos controles de segurança.
3. **Afirmações vencidas.** A doc não pode chamar de "stub" o que já é código
   executando, nem prometer que algo "está pendente" quando foi entregue.
4. **Contagem de adapters.** "14 scanner adapters" escrito no README com 15 na
   fábrica é doc velha do jeito mais fácil de não notar: o número não dá erro, só
   fica errado. Aconteceu quando o Semgrep entrou.

Rodar: `python scripts/check_docs_fresh.py` (exit != 0 reprova).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FALHAS: list[str] = []


def falha(regra: str, detalhe: str) -> None:
    FALHAS.append(f"[{regra}] {detalhe}")


def _ler(rel: str) -> str:
    p = ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ---------------------------------------------------------------- 1. scanners
def check_scanners() -> None:
    pipelines = _ler("orchestrator/jobs/pipelines.py")
    bloco = pipelines.split("factories: dict[str, Any] = {", 1)
    if len(bloco) < 2:
        falha("scanners", "não achei a fábrica de adapters em pipelines.py")
        return
    construiveis = set(re.findall(r'^\s*"([a-z_]+)":\s*lambda', bloco[1], re.MULTILINE))
    if not construiveis:
        falha("scanners", "a fábrica não expõe nenhum scanner — o parser quebrou?")
        return

    docs = _ler("README.md") + _ler("docs/architecture.md")
    for nome in sorted(construiveis):
        if nome not in docs:
            falha(
                "scanners",
                f"'{nome}' é construível no pipeline e não aparece no README nem na "
                "arquitetura — scanner que roda e ninguém documenta",
            )


def check_contagem_de_adapters() -> None:
    """O número anunciado tem que bater com a fábrica.

    A checagem por nome (acima) não pega isto: o Semgrep entrou, ficou documentado na
    tabela, e o README continuou dizendo "14 adapters". Número errado não quebra
    nada — só mente para quem está decidindo se confia na ferramenta.
    """
    pipelines = _ler("orchestrator/jobs/pipelines.py")
    bloco = pipelines.split("factories: dict[str, Any] = {", 1)
    if len(bloco) < 2:
        return  # já reportado por check_scanners
    construiveis = set(re.findall(r'^\s*"([a-z_]+)":\s*lambda', bloco[1], re.MULTILINE))
    # Os de OSINT não estão na fábrica do scan (rodam no pipeline de exposição), mas
    # contam como adapter no README — a conta é sobre os arquivos `*_adapter.py`.
    arquivos = {
        p.stem.removesuffix("_adapter")
        for p in (ROOT / "orchestrator" / "adapters").glob("*_adapter.py")
    }
    total = len(arquivos)
    if not total:
        falha("adapters", "não achei nenhum *_adapter.py — o parser quebrou?")
        return

    textos = {"README.md": _ler("README.md"), "docs/architecture.md": _ler("docs/architecture.md")}
    padrao = re.compile(r"\b(\d{1,3})\s*(?:scanner\s+)?adapters?\b", re.IGNORECASE)
    for arquivo, texto in textos.items():
        for m in padrao.finditer(texto):
            declarado = int(m.group(1))
            if declarado != total:
                falha(
                    "adapters",
                    f"{arquivo} anuncia '{m.group(0)}' e existem {total} arquivos "
                    f"*_adapter.py ({', '.join(sorted(arquivos - construiveis)) or '—'} "
                    "fora da fábrica do scan). Número errado não quebra nada, só mente",
                )


# ------------------------------------------------------------ 2. env / config
def check_env_documentado() -> None:
    config = _ler("orchestrator/config.py")
    corpo = config.split("class Settings", 1)[-1].split("@property", 1)[0]
    campos = set(re.findall(r"^\s{4}([A-Z][A-Z0-9_]{2,}):\s", corpo, re.MULTILINE))
    env_example = _ler(".env.example")
    for campo in sorted(campos):
        if campo not in env_example:
            falha(
                "env",
                f"{campo} existe em Settings e não está no .env.example — opção que "
                "ninguém sabe que pode ligar",
            )


# ------------------------------------------------ 3. afirmações que venceram
_VENCIDAS = [
    (
        "orchestrator/ai/agentic/cai_expert.py",
        "NotImplementedError",
        ["stub", "pendente", "pending"],
        "a doc chama o agente de stub/pendente, mas o código já não tem "
        "NotImplementedError — o loop agêntico existe",
    ),
]


def check_afirmacoes_vencidas() -> None:
    docs = {
        "docs/architecture.md": _ler("docs/architecture.md"),
        "README.md": _ler("README.md"),
    }
    for arquivo_codigo, marca, termos, motivo in _VENCIDAS:
        codigo = _ler(arquivo_codigo)
        # `marca` tem que aparecer como CÓDIGO, não como prosa: o próprio
        # cai_expert.py cita "raise NotImplementedError" num comentário que explica
        # a história, e isso enganaria o gate para sempre.
        if re.search(rf"^\s*raise {re.escape(marca)}", codigo, re.MULTILINE):
            continue  # a afirmação ainda é verdade
        for doc, texto in docs.items():
            for linha_n, linha in enumerate(texto.splitlines(), 1):
                baixa = linha.lower()
                if "cai_expert" in baixa or "agentic" in baixa or "agente" in baixa:
                    if any(t in baixa for t in termos):
                        falha("doc-vencida", f"{doc}:{linha_n} — {motivo}")


def main() -> int:
    check_scanners()
    check_contagem_de_adapters()
    check_env_documentado()
    check_afirmacoes_vencidas()

    if not FALHAS:
        print("doc em dia: scanners, variáveis e afirmações batem com o código.")
        return 0
    print("DOCUMENTAÇÃO DESATUALIZADA — o código andou e a doc ficou para trás:\n")
    for f in FALHAS:
        print(f"  {f}")
    print(f"\n{len(FALHAS)} divergência(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
