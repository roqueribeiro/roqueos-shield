"""Evidência redigida para o que fica em repouso fora do armazém de evidência.

O armazém (`orchestrator.evidence.store`) já grava o corpo redigido (ou o original
cifrado, por opção). Mas a evidência do scanner também ia CRUA para outros dois lugares
em repouso: o `findings.payload` (o `Finding` inteiro, com o `Evidence`) e o relatório
técnico HTML gravado em disco e servido por `GET /reports/{id}`. Um CPF, cookie ou
token capturado numa resposta HTTP ficava em claro no banco e num arquivo, mesmo com o
armazém redigido.

Aqui só se APLICA o scrubber existente (`domain/scrubber.py` não muda): o que vai para o
disco é mais privado, nunca menos. A captura de evidência continua recebendo o `Finding`
original, porque é ela que decide entre redigir e cifrar o original.
"""

from __future__ import annotations

from orchestrator.domain.schemas import Evidence, Finding
from orchestrator.domain.scrubber import scrub

_CAMPOS_DE_TEXTO = ("description", "request", "response", "payload", "snippet")


def evidencia_redigida(ev: Evidence) -> Evidence:
    mudancas = {
        campo: scrub(valor) for campo in _CAMPOS_DE_TEXTO if (valor := getattr(ev, campo, None))
    }
    return ev.model_copy(update=mudancas)


def finding_redigido(f: Finding) -> Finding:
    """Cópia do achado com o texto das evidências redigido. O original fica intacto."""
    if not f.evidence:
        return f
    return f.model_copy(update={"evidence": [evidencia_redigida(e) for e in f.evidence]})
