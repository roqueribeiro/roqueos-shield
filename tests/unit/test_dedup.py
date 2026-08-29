"""Tests for heuristic dedup."""

from __future__ import annotations

from uuid import uuid4

from orchestrator.domain.dedup import heuristic_dedup
from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Evidence,
    Finding,
    Severity,
    Target,
)


def _mk(value: str, rule: str, severity: Severity) -> Finding:
    return Finding(
        scan_id=uuid4(),
        target=Target(asset_type=AssetType.URL, value=value),
        source_tool="zap",
        source_rule_id=rule,
        title="t",
        description="d",
        severity=severity,
        confidence=Confidence.FIRM,
        evidence=[Evidence(description="e")],
    )


def test_keeps_higher_severity() -> None:
    a = _mk("http://x", "1", Severity.LOW)
    b = _mk("http://x", "1", Severity.HIGH)  # mesmo deduped_key
    out = heuristic_dedup([a, b])
    assert len(out) == 1
    assert out[0].severity == Severity.HIGH


def test_distinct_keys_preserved() -> None:
    a = _mk("http://x", "1", Severity.LOW)
    b = _mk("http://x", "2", Severity.LOW)
    out = heuristic_dedup([a, b])
    assert len(out) == 2


def test_empty_list() -> None:
    assert heuristic_dedup([]) == []


def test_identical_findings_dedup_to_one() -> None:
    a = _mk("http://x", "1", Severity.MEDIUM)
    b = _mk("http://x", "1", Severity.MEDIUM)
    c = _mk("http://x", "1", Severity.MEDIUM)
    out = heuristic_dedup([a, b, c])
    assert len(out) == 1


# ============================= dedupe não pode APAGAR achado depois de encontrado


def test_dois_parametros_da_mesma_url_nao_colapsam() -> None:
    """O ZAP alerta por PARÂMETRO.

    XSS refletido em `?q=` e em `?sort=` da mesma URL têm o mesmo `pluginId` e o
    mesmo `target.value`: a chave colidia e um dos dois era descartado sem registro.
    O vetor não vira "limpo" (sobra um), mas a contagem que vai para o relatório fica
    menor que a realidade, e um achado desaparece DEPOIS de já ter sido encontrado.
    """
    from uuid import uuid4

    from orchestrator.domain.dedup import heuristic_dedup
    from orchestrator.domain.schemas import (
        AssetType,
        Confidence,
        Finding,
        Severity,
        Target,
    )

    sid = uuid4()

    def _f(param: str) -> Finding:
        return Finding(
            scan_id=sid,
            target=Target(asset_type=AssetType.URL, value="https://app.test/busca"),
            source_tool="zap",
            source_rule_id="40012",
            dedup_discriminator=param,
            title="XSS refletido",
            description="d",
            severity=Severity.HIGH,
            confidence=Confidence.FIRM,
        )

    saida = heuristic_dedup([_f("q"), _f("sort")])
    assert len(saida) == 2, "dois parâmetros diferentes colapsaram num achado só"


def test_o_mesmo_achado_duas_vezes_continua_deduplicando() -> None:
    """O discriminador não pode desligar o dedupe de verdade."""
    from uuid import uuid4

    from orchestrator.domain.dedup import heuristic_dedup
    from orchestrator.domain.schemas import (
        AssetType,
        Confidence,
        Finding,
        Severity,
        Target,
    )

    sid = uuid4()

    def _f() -> Finding:
        return Finding(
            scan_id=sid,
            target=Target(asset_type=AssetType.URL, value="https://app.test/busca"),
            source_tool="zap",
            source_rule_id="40012",
            dedup_discriminator="q",
            title="XSS refletido",
            description="d",
            severity=Severity.HIGH,
            confidence=Confidence.FIRM,
        )

    assert len(heuristic_dedup([_f(), _f()])) == 1
