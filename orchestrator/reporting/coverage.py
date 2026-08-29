"""A cobertura, calculada em UM lugar só.

Três superfícies mostram cobertura ao usuário — o Fix Bundle, o relatório executivo
e a API/UI — e cada uma tinha a sua própria conta. Deu no que sempre dá: o bundle
aprendeu a dizer "COBERTURA DESCONHECIDA" quando não há dado, o executivo continuou
tratando `pulados == {}` como "tudo rodou", e a UI seguiu listando o que foi PEDIDO.
Três telas do mesmo produto, três respostas para a mesma pergunta.

`pulados` vazio significa DUAS coisas opostas — "nada foi pulado" e "não tenho o
dado" — e é a distinção que decide se a nota A do relatório vale alguma coisa. Ela
mora aqui, e só aqui.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class Cobertura(StrEnum):
    COMPLETA = "completa"
    INCOMPLETA = "incompleta"
    DESCONHECIDA = "desconhecida"


def resumo(fonte: Any) -> dict[str, Any]:
    """Resumo de cobertura de um `ScanRow` ou de um `ScanResult`.

    Aceita os dois porque o relatório é gerado das duas origens: do resultado em
    memória (worker) e da linha persistida (API).
    """
    rodaram = list(getattr(fonte, "scanners_ran", None) or [])
    pulados = dict(getattr(fonte, "scanners_skipped", None) or {})
    pedidos = list(getattr(fonte, "requested_scanners", None) or [])

    if not rodaram and not pulados:
        # Nem executado nem pulado: o scan não registrou cobertura. Linha anterior à
        # migration 0007, scan ainda em andamento, ou falha ao persistir (o
        # `_persist_findings` é best-effort de propósito). Dizer "completa" aqui é a
        # mentira mais confortável possível — e era o que o executivo fazia.
        estado = Cobertura.DESCONHECIDA
    elif pulados:
        estado = Cobertura.INCOMPLETA
    else:
        estado = Cobertura.COMPLETA

    return {
        "estado": estado.value,
        "completa": estado is Cobertura.COMPLETA,
        "desconhecida": estado is Cobertura.DESCONHECIDA,
        "rodaram": rodaram,
        "pulados": pulados,
        "pedidos": pedidos,
        "nota": _nota(estado, rodaram, pulados),
    }


def _nota(estado: Cobertura, rodaram: list[str], pulados: dict[str, str]) -> str:
    if estado is Cobertura.DESCONHECIDA:
        return (
            "COBERTURA DESCONHECIDA: este scan não registrou quais scanners rodaram. "
            "Não é possível afirmar que os vetores pedidos foram verificados — "
            "trate os números abaixo como incompletos."
        )
    if estado is Cobertura.COMPLETA:
        return f"Cobertura completa: {', '.join(rodaram)} executaram sem falha."
    if not rodaram:
        return (
            "COBERTURA NULA: NENHUM scanner foi executado. Os números são zero porque "
            "nada foi verificado, não porque o alvo está limpo."
        )
    return (
        f"COBERTURA INCOMPLETA: {', '.join(sorted(pulados))} não rodaram. "
        "Zero achados destes vetores NÃO significa alvo limpo."
    )
