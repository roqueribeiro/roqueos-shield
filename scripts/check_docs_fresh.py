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

5. **A forma da documentação** (padrão do aidlc-harness). Todo doc em inglês tem o
   par em português (e vice-versa) pela tabela `PARES`, as duas linhas de idioma que
   apontam um para o outro, entrada no INDEX do idioma; doc fora da tabela reprova; e
   todo link e âncora entre os docs resolve, assim como todo `docs/*.md` citado no
   código. Doc em dois idiomas sem isso diverge calado: o par fica velho, o link
   quebra numa renomeação e ninguém percebe até o leitor cair nele.

Rodar: `python scripts/check_docs_fresh.py` (exit != 0 reprova).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARQUITETURA = "docs/ARCHITECTURE.md"
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

    docs = _ler("README.md") + _ler(ARQUITETURA)
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

    textos = {"README.md": _ler("README.md"), ARQUITETURA: _ler(ARQUITETURA)}
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
        ARQUITETURA: _ler(ARQUITETURA),
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


def check_versao_do_instalador() -> None:
    """O `install.sh` sobe a imagem da versão do repo.

    O comando de um passo que o README manda rodar lê o script da `main`. Se a versão
    fixa nele ficar para trás, quem instala hoje recebe a imagem de meses atrás, e
    nada dá erro: só fica velho. Sobe junto com o `pyproject.toml` ou o gate reprova.
    """
    m = re.search(r'^version = "([^"]+)"', _ler("pyproject.toml"), re.MULTILINE)
    if not m:
        falha("versao", "não achei a versão no pyproject.toml")
        return
    alvo = m.group(1)
    # Cada lugar que diz a versão, e o que ele deveria dizer. O /health respondia
    # 0.5.0 com o __init__ em 0.1.0 e ninguém via (revisão de 07/11/2026).
    lugares = {
        "install.sh (VERSAO_PADRAO)": (r'^VERSAO_PADRAO="v([^"]+)"', "install.sh"),
        "orchestrator/__init__.py": (r'^__version__ = "([^"]+)"', "orchestrator/__init__.py"),
        "web/package.json": (r'^  "version": "([^"]+)"', "web/package.json"),
        # O banner do README escreve a versão nos chips; a imagem fica velha calada se
        # ninguém regera. O gen.py grava aqui para qual versão gerou.
        "banner do README (rode docs/assets/marca/gen.py)": (
            r'^  "versao_gerada": "([^"]*)"',
            "docs/assets/marca/carimbo.json",
        ),
    }
    for nome, (rx, arq) in lugares.items():
        achou = re.search(rx, _ler(arq), re.MULTILINE)
        if not achou:
            falha("versao", f"não achei a versão em {nome}")
        elif achou.group(1) != alvo:
            falha("versao", f"{nome} diz {achou.group(1)}, o pyproject está em {alvo}")


# ------------------------------------------------- 5. a forma da documentação
# EN é a versão principal; PT é a tradução. Doc novo entra aqui ou o gate reprova.
PARES: dict[str, str] = {
    "README.md": "README.pt-BR.md",
    "CONTRIBUTING.md": "docs/pt-BR/CONTRIBUTING.md",
    "docs/INDEX.md": "docs/pt-BR/INDEX.md",
    "docs/GETTING-STARTED.md": "docs/pt-BR/COMECAR.md",
    "docs/OPERATIONS.md": "docs/pt-BR/OPERACAO.md",
    "docs/WHEN-IT-BREAKS.md": "docs/pt-BR/QUANDO-QUEBRA.md",
    "docs/ARCHITECTURE.md": "docs/pt-BR/ARQUITETURA.md",
    "docs/INTEGRATIONS.md": "docs/pt-BR/INTEGRACOES.md",
    "docs/AI-FIX-BUNDLE.md": "docs/pt-BR/AI-FIX-BUNDLE.md",
    "docs/REFERENCE.md": "docs/pt-BR/REFERENCIA.md",
    "docs/GLOSSARY.md": "docs/pt-BR/GLOSSARIO.md",
    "docs/THREAT-MODEL.md": "docs/pt-BR/MODELO-DE-AMEACAS.md",
    "docs/DEVELOPMENT.md": "docs/pt-BR/DESENVOLVIMENTO.md",
    "docs/TESTING.md": "docs/pt-BR/CRITERIOS-DE-TESTE.md",
    "docs/EXTENDING.md": "docs/pt-BR/ESTENDER.md",
}
# Os READMEs têm o seletor de idioma no próprio cabeçalho, não a linha em itálico.
_SEM_LINHA_DE_IDIOMA = {"README.md", "README.pt-BR.md"}
# Só existem em inglês, como no aidlc-harness: política, conduta, histórico.
_SO_EM_INGLES = {"SECURITY.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md"}


def _rel(de: str, para: str) -> str:
    import os.path

    return os.path.relpath(para, os.path.dirname(de) or ".").replace("\\", "/")


def _slug(titulo: str) -> str:
    """Âncora como o GitHub gera: minúsculas, sem pontuação (acento fica), espaço vira -."""
    t = re.sub(r"<[^>]+>", "", titulo)  # tags html
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)  # [texto](link) -> texto
    t = t.replace("`", "").strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def _sem_codigo(texto: str) -> str:
    """Tira blocos ``` e código inline: link e título dentro de código não contam."""
    texto = re.sub(r"^```.*?^```", "", texto, flags=re.MULTILINE | re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", texto)


def _ancoras(texto: str) -> set[str]:
    vistas: dict[str, int] = {}
    ancoras: set[str] = set()
    for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", _sem_codigo(texto), re.MULTILINE):
        base = _slug(m.group(1))
        n = vistas.get(base, 0)
        vistas[base] = n + 1
        ancoras.add(base if n == 0 else f"{base}-{n}")
    ancoras |= set(re.findall(r'<a\s+(?:id|name)="([^"]+)"', texto))
    return ancoras


def _docs_publicos() -> list[str]:
    raiz = ["README.md", "README.pt-BR.md", "CONTRIBUTING.md", "SECURITY.md"]
    docs = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs").rglob("*.md"))
    return [d for d in raiz if (ROOT / d).exists()] + docs


def check_forma_dos_docs() -> None:
    pt_para_en = {pt: en for en, pt in PARES.items()}
    # 1. todo doc publicado está na tabela (ou é do conjunto só em inglês / da marca)
    for doc in _docs_publicos():
        if doc.startswith("docs/assets/"):
            continue
        if doc not in PARES and doc not in pt_para_en and doc not in _SO_EM_INGLES:
            falha(
                "docs-forma",
                f"{doc} não está em PARES: doc novo entra com o par em pt-BR e no INDEX, "
                "ou some do repo",
            )
    for en, pt in PARES.items():
        # 2. os dois lados existem
        for lado in (en, pt):
            if not (ROOT / lado).exists():
                falha("docs-forma", f"{lado} não existe (par de {en} ↔ {pt})")
        if not ((ROOT / en).exists() and (ROOT / pt).exists()):
            continue
        # 3. linha de idioma apontando para o par, logo no começo
        if en not in _SEM_LINHA_DE_IDIOMA:
            topo_en = "\n".join(_ler(en).splitlines()[:6])
            alvo = _rel(en, pt)
            if f"*Also available in [Brazilian Portuguese]({alvo})" not in topo_en:
                falha(
                    "docs-forma",
                    f"{en}: falta, logo abaixo do título, "
                    f"'*Also available in [Brazilian Portuguese]({alvo}).*'",
                )
            topo_pt = "\n".join(_ler(pt).splitlines()[:6])
            volta = _rel(pt, en)
            nome = en.rsplit("/", 1)[-1]
            if f"*Tradução de [{nome}]({volta}), a versão principal, em inglês." not in topo_pt:
                falha(
                    "docs-forma",
                    f"{pt}: falta, logo abaixo do título, '*Tradução de "
                    f"[{nome}]({volta}), a versão principal, em inglês. Se as duas "
                    "divergirem, vale a em inglês.*'",
                )
    # 4. o INDEX de cada idioma lista todo doc daquele idioma
    for indice, idioma in (("docs/INDEX.md", 0), ("docs/pt-BR/INDEX.md", 1)):
        texto = _ler(indice)
        if not texto:
            continue
        for en, pt in PARES.items():
            doc = (en, pt)[idioma]
            if doc == indice or doc.startswith("README"):
                continue
            if f"]({_rel(indice, doc)}" not in texto:
                falha("docs-forma", f"{indice} não leva a {doc}")


_LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|(?:src|srcset|href)=\"([^\"]+)\"")


def check_links_dos_docs() -> None:
    cache: dict[str, set[str]] = {}
    for doc in _docs_publicos():
        texto = _sem_codigo(_ler(doc))
        for m in _LINK.finditer(texto):
            alvo = (m.group(1) or m.group(2) or "").strip()
            if not alvo or re.match(r"^[a-z][a-z0-9+.-]*:", alvo):  # http:, mailto:...
                continue
            caminho, _, ancora = alvo.partition("#")
            if caminho:
                destino = (ROOT / doc).parent / caminho
                try:
                    destino = destino.resolve()
                    rel = destino.relative_to(ROOT).as_posix()
                except (OSError, ValueError):
                    falha("docs-link", f"{doc}: link para fora do repo: {alvo}")
                    continue
                if not destino.exists():
                    falha("docs-link", f"{doc}: link quebrado: {alvo}")
                    continue
            else:
                rel = doc
            if ancora and rel.endswith(".md"):
                if rel not in cache:
                    cache[rel] = _ancoras(_ler(rel))
                if ancora not in cache[rel]:
                    falha("docs-link", f"{doc}: âncora inexistente: {alvo}")


def check_docs_citados_no_codigo() -> None:
    """Caminho de doc (`docs/<nome>.md`) citado em código, script ou regra tem que existir.

    Descrição de rota (vira o Swagger), docstring de exportador, texto de diagrama:
    renomear o doc sem isto deixa o usuário com um caminho que não existe.
    """
    import subprocess

    try:
        rastreados = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return
    for arq in rastreados:
        if arq.endswith((".md", ".svg", ".webp", ".png", ".jpg", ".ttf", ".lock")):
            continue
        try:
            texto = (ROOT / arq).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for citado in sorted(set(re.findall(r"\bdocs/[A-Za-z0-9_./-]+\.md\b", texto))):
            if not (ROOT / citado).exists():
                falha("docs-citado", f"{arq} cita {citado}, que não existe")


def main() -> int:
    check_scanners()
    check_contagem_de_adapters()
    check_env_documentado()
    check_afirmacoes_vencidas()
    check_versao_do_instalador()
    check_forma_dos_docs()
    check_links_dos_docs()
    check_docs_citados_no_codigo()

    if not FALHAS:
        print(
            "doc em dia: scanners, variáveis e afirmações batem com o código; "
            "pares, índices, links e âncoras resolvem."
        )
        return 0
    print("DOCUMENTAÇÃO DESATUALIZADA — o código andou e a doc ficou para trás:\n")
    for f in FALHAS:
        print(f"  {f}")
    print(f"\n{len(FALHAS)} divergência(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
