"""Deduplicação de findings — heurística + AI semântica.

Heurística (rápida, deterministica): mesmo `deduped_key` → merge.
Semântica (LLM): findings de tools diferentes que descrevem o mesmo problema.
Ex: ZAP "SQL Injection" + sqlmap confirmation = 1 só.
"""

from __future__ import annotations

from collections.abc import Iterable

import structlog

from orchestrator.ai.gateway import complete_json
from orchestrator.domain.schemas import Finding

log = structlog.get_logger(__name__)


_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_CONFIDENCE_RANK = {"certain": 2, "firm": 1, "tentative": 0}


def _peso(f: Finding) -> tuple[int, int, str, str, str]:
    """Quem fica num empate de `deduped_key`, sem depender da ordem de chegada.

    Severity maior, depois confidence maior, depois o menor (source_tool,
    source_rule_id, id): um critério total. Antes o empate ficava com o primeiro que
    chegou, e a ordem de chegada é a dos adapters e a de cada scanner (alertas do
    ZAP, JSONL do nuclei), que não é garantida. O mesmo scan podia gravar um achado
    num rescan e outro no seguinte.
    """
    return (
        _SEVERITY_RANK.get(str(f.severity), 0),
        _CONFIDENCE_RANK.get(str(f.confidence), 0),
        # nos três últimos, a MENOR string ganha (ver `_ganha`)
        f.source_tool,
        f.source_rule_id or "",
        str(f.id),
    )


def heuristic_dedup(findings: Iterable[Finding]) -> list[Finding]:
    """Um achado por `deduped_key`, escolhido e ordenado de forma determinística.

    Fica o de maior severity (desempate: confidence, depois source_tool,
    source_rule_id e id). A saída sai ordenada por severity decrescente e depois por
    `deduped_key`: a mesma entrada, em qualquer ordem, dá a mesma lista.
    """
    lista = list(findings)
    keep: dict[str, Finding] = {}
    for f in lista:
        if not f.deduped_key:
            continue
        existing = keep.get(f.deduped_key)
        if existing is None or _ganha(f, existing):
            keep[f.deduped_key] = f

    deduped = sorted(
        keep.values(),
        key=lambda f: (-_SEVERITY_RANK.get(str(f.severity), 0), f.deduped_key),
    )
    log.info("dedup.heuristic_done", before=len(lista), after=len(deduped))
    return deduped


def _ganha(novo: Finding, atual: Finding) -> bool:
    a, b = _peso(novo), _peso(atual)
    if a[:2] != b[:2]:
        return a[:2] > b[:2]
    return a[2:] < b[2:]


_SEMANTIC_PROMPT = """\
Você receberá uma lista de findings de scanners de segurança. Alguns descrevem o
MESMO problema visto por tools diferentes (ex.: ZAP "SQL Injection" + Nuclei
"sql-injection-mysql" + Greenbone "Generic SQL Injection" no mesmo endpoint).

Retorne JSON com clusters semanticamente equivalentes:

{
  "clusters": [
    { "primary_id": "<finding_id>", "duplicate_ids": ["<id1>", "<id2>"] }
  ]
}

Regras:
- Cluster só se for o MESMO problema no MESMO ativo. Endpoints diferentes = findings diferentes.
- primary_id = o de maior confidence/severity.
- Se um finding for único, NÃO inclua no resultado.
"""


async def semantic_dedup(findings: list[Finding], *, model: str | None = None) -> list[Finding]:
    """Usa LLM para agrupar findings semanticamente equivalentes.

    Mantém o "primary" e descarta os duplicados (com merge de evidências).
    """

    if len(findings) < 2:
        return findings

    import json

    summary = [
        {
            "id": str(f.id),
            "tool": f.source_tool,
            "rule_id": f.source_rule_id,
            "vuln_id": f.vuln_id,
            "title": f.title,
            "target": f.target.value,
            "severity": f.severity,
            "confidence": f.confidence,
        }
        for f in findings
    ]

    try:
        response = await complete_json(
            [
                {"role": "system", "content": _SEMANTIC_PROMPT},
                {
                    "role": "user",
                    "content": "FINDINGS:\n" + json.dumps(summary, ensure_ascii=False),
                },
            ],
            model=model,
            cache_system=True,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("dedup.semantic_failed", error=str(e))
        return findings

    by_id = {str(f.id): f for f in findings}
    discard: set[str] = set()
    for cluster in response.get("clusters", []):
        primary = cluster.get("primary_id")
        dups = cluster.get("duplicate_ids", [])
        if primary not in by_id:
            continue
        primary_finding = by_id[primary]
        for dup_id in dups:
            if dup_id == primary or dup_id not in by_id:
                continue
            dup = by_id[dup_id]
            # merge evidências
            primary_finding.evidence.extend(dup.evidence)
            discard.add(dup_id)

    out = [f for f in findings if str(f.id) not in discard]
    log.info("dedup.semantic_done", before=len(findings), after=len(out), discarded=len(discard))
    return out
