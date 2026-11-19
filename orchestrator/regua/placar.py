"""Gabarito, placar e linha de base da régua de detecção.

Três regras carregam o resto:

1. **Detectar pelo motivo certo.** Um defeito só conta como achado se um scanner da
   camada dele disparar NO ARQUIVO dele E pela regra esperada (CWE ou padrão de regra).
   O checkov reclama de dez coisas num bucket S3; só a ACL pública prova que ele viu o
   defeito plantado.
2. **Alarme em código limpo é falso positivo.** O gabarito tem controles limpos (SQL
   parametrizado, `subprocess` com lista, `yaml.safe_load`). Sem eles a régua só mediria
   recall, e uma ferramenta que marcasse tudo tiraria 100%.
3. **Classificar certo é uma medida à parte.** Um defeito achado com a CWE errada conta
   como detectado (a regra prova o motivo), mas não como classificado: é a CWE que vira
   a categoria OWASP/PCI/LGPD do relatório de compliance.
4. **Não medido não é zero nem cem.** Camada cujo scanner não rodou (ausente, pulado)
   sai como `não medida`, com o motivo. É o contrato do silêncio aplicado à própria
   medição: o gate local imprimia `PASSOU` para a efetividade com o teste pulado.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from orchestrator.domain.schemas import Finding


class Camada(BaseModel):
    scanners: list[str]


class Item(BaseModel):
    id: str
    camada: str
    tipo: Literal["defeito", "limpo"]
    arquivo: str
    descricao: str
    # Critério de "pelo motivo certo". Vazio nos dois = qualquer achado no arquivo conta.
    cwe: list[str] = Field(default_factory=list)
    regra: str | None = None


class Gabarito(BaseModel):
    nome: str
    descricao: str
    camadas: dict[str, Camada]
    itens: list[Item]

    @classmethod
    def carregar(cls, caminho: Path) -> Gabarito:
        return cls.model_validate(yaml.safe_load(caminho.read_text(encoding="utf-8")))

    def camada_do_scanner(self, scanner: str) -> str | None:
        for nome, c in self.camadas.items():
            if scanner in c.scanners:
                return nome
        return None


class ResultadoItem(BaseModel):
    id: str
    camada: str
    tipo: str
    arquivo: str
    descricao: str
    detectado: bool | None  # None = camada não medida
    # Algum achado no arquivo trouxe a CWE esperada? None = o item não define CWE.
    cwe_correta: bool | None = None
    achados: list[str] = Field(default_factory=list)  # regras que dispararam no arquivo


class PlacarCamada(BaseModel):
    camada: str
    medida: bool
    motivo_nao_medida: str | None = None
    defeitos: int
    detectados: int
    recall: float | None  # None quando não medida
    falsos_positivos: int
    nao_detectados: list[str] = Field(default_factory=list)
    # Classificação: dos detectados que definem CWE, quantos saíram com a CWE certa.
    classificaveis: int = 0
    bem_classificados: int = 0
    classificacao: float | None = None
    mal_classificados: list[str] = Field(default_factory=list)


class Placar(BaseModel):
    gabarito: str
    camadas: dict[str, PlacarCamada]
    itens: list[ResultadoItem]
    fora_do_gabarito: list[str]  # achados em arquivos que o gabarito não cobre
    scanners_rodaram: list[str]
    scanners_pulados: dict[str, str]


def _arquivo_do_achado(f: Finding, raiz: str | None) -> str:
    """`target.value` dos adapters de repo é `arquivo:linha`; devolve o arquivo relativo."""
    valor = f.target.value
    caminho = valor.rsplit(":", 1)[0] if re.search(r":\d+$|:\?$", valor) else valor
    if raiz and caminho.startswith(raiz):
        caminho = caminho[len(raiz) :]
    return caminho.lstrip("/")


def _pelo_motivo_certo(item: Item, f: Finding) -> bool:
    if not item.cwe and not item.regra:
        return True
    if item.cwe and any(c in f.cwe for c in item.cwe):
        return True
    alvo = f"{f.source_rule_id or ''} {f.title}"
    return bool(item.regra and re.search(item.regra, alvo))


def avaliar(
    gabarito: Gabarito,
    findings: list[Finding],
    *,
    scanners_ran: list[str],
    scanners_skipped: dict[str, str],
    raiz: str | None = None,
) -> Placar:
    """Placar do gabarito contra os achados de um scan."""
    por_arquivo: dict[str, list[Finding]] = {}
    for f in findings:
        por_arquivo.setdefault(_arquivo_do_achado(f, raiz), []).append(f)

    medidas: dict[str, tuple[bool, str | None]] = {}
    for nome, c in gabarito.camadas.items():
        rodou = [s for s in c.scanners if s in scanners_ran]
        if rodou:
            medidas[nome] = (True, None)
        else:
            motivos = [f"{s}: {scanners_skipped[s]}" for s in c.scanners if s in scanners_skipped]
            medidas[nome] = (False, "; ".join(motivos) or f"nenhum de {c.scanners} rodou")

    itens: list[ResultadoItem] = []
    fp_por_camada: dict[str, int] = dict.fromkeys(gabarito.camadas, 0)
    for item in gabarito.itens:
        no_arquivo = por_arquivo.get(item.arquivo, [])
        regras = sorted({f.source_rule_id or f.title for f in no_arquivo})
        if item.tipo == "limpo":
            for f in no_arquivo:
                camada = gabarito.camada_do_scanner(f.source_tool)
                if camada:
                    fp_por_camada[camada] += 1
            itens.append(
                ResultadoItem(
                    **item.model_dump(include={"id", "camada", "tipo", "arquivo", "descricao"}),
                    detectado=bool(no_arquivo),
                    achados=regras,
                )
            )
            continue
        scanners_da_camada = set(gabarito.camadas[item.camada].scanners)
        da_camada = [f for f in no_arquivo if f.source_tool in scanners_da_camada]
        cwe_correta: bool | None = None
        if not medidas[item.camada][0]:
            detectado: bool | None = None
        else:
            detectado = any(_pelo_motivo_certo(item, f) for f in da_camada)
            if item.cwe and detectado:
                cwe_correta = any(c in f.cwe for f in da_camada for c in item.cwe)
        itens.append(
            ResultadoItem(
                **item.model_dump(include={"id", "camada", "tipo", "arquivo", "descricao"}),
                detectado=detectado,
                cwe_correta=cwe_correta,
                achados=regras,
            )
        )

    camadas: dict[str, PlacarCamada] = {}
    for nome in gabarito.camadas:
        defeitos = [i for i in itens if i.camada == nome and i.tipo == "defeito"]
        medida, motivo = medidas[nome]
        detectados = sum(1 for i in defeitos if i.detectado)
        classificaveis = [i for i in defeitos if i.cwe_correta is not None]
        bem = sum(1 for i in classificaveis if i.cwe_correta)
        camadas[nome] = PlacarCamada(
            camada=nome,
            medida=medida,
            motivo_nao_medida=motivo,
            defeitos=len(defeitos),
            detectados=detectados if medida else 0,
            recall=(detectados / len(defeitos) if defeitos else None) if medida else None,
            falsos_positivos=fp_por_camada[nome],
            nao_detectados=[i.id for i in defeitos if medida and not i.detectado],
            classificaveis=len(classificaveis),
            bem_classificados=bem,
            classificacao=(bem / len(classificaveis)) if classificaveis else None,
            mal_classificados=[i.id for i in classificaveis if not i.cwe_correta],
        )

    cobertos = {i.arquivo for i in gabarito.itens}
    fora = sorted(
        f"{arquivo} ({f.source_tool}: {f.source_rule_id or f.title})"
        for arquivo, fs in por_arquivo.items()
        if arquivo not in cobertos
        for f in fs
    )
    return Placar(
        gabarito=gabarito.nome,
        camadas=camadas,
        itens=itens,
        fora_do_gabarito=fora,
        scanners_rodaram=list(scanners_ran),
        scanners_pulados=dict(scanners_skipped),
    )


# ------------------------------------------------------------ linha de base


def comparar_com_linha_de_base(
    placar: Placar, linha: dict[str, Any], *, exigir_medida: bool
) -> list[str]:
    """Regressões contra a linha de base (catraca: recall só sobe, FP só desce).

    `exigir_medida`: camada sem medida reprova (o modo do CI, onde os scanners estão
    instalados de propósito). Localmente fica só o aviso, para não punir quem não tem
    o scanner, mas nunca vira verde em silêncio."""
    base = linha.get(placar.gabarito, {})
    problemas: list[str] = []
    for nome, pc in placar.camadas.items():
        alvo = base.get(nome)
        if alvo is None:
            problemas.append(f"{nome}: camada sem linha de base (registre com --atualizar)")
            continue
        if not pc.medida:
            if exigir_medida:
                problemas.append(f"{nome}: não medida ({pc.motivo_nao_medida})")
            continue
        if pc.recall is not None and pc.recall + 1e-9 < alvo["recall_min"]:
            problemas.append(
                f"{nome}: recall caiu para {pc.recall:.0%} "
                f"(linha de base {alvo['recall_min']:.0%}); "
                f"não detectados: {', '.join(pc.nao_detectados)}"
            )
        cls_min = alvo.get("classificacao_min")
        if (
            cls_min is not None
            and pc.classificacao is not None
            and pc.classificacao + 1e-9 < cls_min
        ):
            problemas.append(
                f"{nome}: classificação (CWE certa) caiu para {pc.classificacao:.0%} "
                f"(linha de base {cls_min:.0%}); "
                f"mal classificados: {', '.join(pc.mal_classificados)}"
            )
        if pc.falsos_positivos > alvo["fp_max"]:
            problemas.append(
                f"{nome}: falsos positivos subiram para {pc.falsos_positivos} "
                f"(linha de base {alvo['fp_max']})"
            )
    return problemas


def nova_linha_de_base(placar: Placar, linha: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Grava o placar como linha de base, mas só no sentido da catraca: piorar exige
    editar o arquivo à mão, com o motivo no commit."""
    base = dict(linha.get(placar.gabarito, {}))
    recusas: list[str] = []
    for nome, pc in placar.camadas.items():
        if not pc.medida or pc.recall is None:
            recusas.append(f"{nome}: não medida, linha de base mantida")
            continue
        antes = base.get(nome)
        if antes and (
            pc.recall + 1e-9 < antes["recall_min"] or pc.falsos_positivos > antes["fp_max"]
        ):
            recusas.append(f"{nome}: o placar piorou; a catraca não grava piora automaticamente")
            continue
        if (
            antes
            and pc.classificacao is not None
            and antes.get("classificacao_min") is not None
            and pc.classificacao + 1e-9 < antes["classificacao_min"]
        ):
            recusas.append(f"{nome}: a classificação piorou; a catraca não grava piora")
            continue
        base[nome] = {"recall_min": round(pc.recall, 4), "fp_max": pc.falsos_positivos}
        if pc.classificacao is not None:
            base[nome]["classificacao_min"] = round(pc.classificacao, 4)
    nova = dict(linha)
    nova[placar.gabarito] = base
    return nova, recusas


# ------------------------------------------------------------ relatório


def _pct(v: float | None) -> str:
    return "não medido" if v is None else f"{v:.0%}"


def markdown(placar: Placar) -> str:
    linhas = [
        f"## Régua de detecção: `{placar.gabarito}`",
        "",
        "| Camada | Recall | Detectados | Classificação (CWE certa) | Falsos positivos "
        "| Situação |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for pc in placar.camadas.values():
        situacao = "medida" if pc.medida else f"NÃO MEDIDA: {pc.motivo_nao_medida}"
        cls = (
            f"{_pct(pc.classificacao)} ({pc.bem_classificados}/{pc.classificaveis})"
            if pc.classificaveis
            else "n/a"
        )
        linhas.append(
            f"| {pc.camada} | {_pct(pc.recall)} | {pc.detectados}/{pc.defeitos} | {cls} | "
            f"{pc.falsos_positivos} | {situacao} |"
        )
    perdidos = [i for i in placar.itens if i.tipo == "defeito" and i.detectado is False]
    if perdidos:
        linhas += ["", "**Defeitos não detectados**", ""]
        linhas += [f"- `{i.id}` {i.descricao} (`{i.arquivo}`)" for i in perdidos]
    mal = [i for i in placar.itens if i.cwe_correta is False]
    if mal:
        linhas += ["", "**Detectados com a CWE errada (classificação)**", ""]
        linhas += [f"- `{i.id}` {i.descricao}: regras {', '.join(i.achados)}" for i in mal]
    falsos = [i for i in placar.itens if i.tipo == "limpo" and i.achados]
    if falsos:
        linhas += ["", "**Alarmes em código limpo (falsos positivos)**", ""]
        linhas += [f"- `{i.id}` {i.arquivo}: {', '.join(i.achados)}" for i in falsos]
    if placar.fora_do_gabarito:
        linhas += ["", "**Achados fora do gabarito**", ""]
        linhas += [f"- {x}" for x in placar.fora_do_gabarito]
    return "\n".join(linhas) + "\n"


def salvar(placar: Placar, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"regua-{placar.gabarito}.json").write_text(
        json.dumps(placar.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (destino / f"regua-{placar.gabarito}.md").write_text(markdown(placar), encoding="utf-8")
