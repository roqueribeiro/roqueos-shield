"""Cobertura declarada: "não rodou" nunca pode parecer "não achou".

Três bugs desta sessão foram a mesma coisa — a ferramenta reporta zero e o leitor
conclui que o alvo está limpo. Este arquivo trava a correção estrutural: um scanner
que não rodou aparece no resultado, no bundle, e no log.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestrator.domain.schemas import AssetType, Target
from orchestrator.jobs.pipelines import AdapterUnavailableError, ScanResult, _run_adapter
from orchestrator.reporting.exporters.ai_bundle import _coverage


class _Unhealthy:
    name = "trivy"

    async def health(self) -> bool:
        return False  # binário ausente / serviço fora do ar


async def test_unhealthy_adapter_raises_instead_of_returning_empty() -> None:
    """Antes: `return []` — o scan seguia 'com sucesso' e o vetor sumia."""
    with pytest.raises(AdapterUnavailableError, match="NÃO verificou"):
        await _run_adapter(_Unhealthy(), Target(asset_type=AssetType.IMAGE, value="alpine"), {})


def test_scan_result_knows_its_coverage() -> None:
    r = ScanResult(
        scan_id=__import__("uuid").uuid4(), target=Target(asset_type=AssetType.IMAGE, value="x")
    )
    assert r.coverage_is_complete
    r.scanners_skipped["trivy"] = "binário ausente"
    assert not r.coverage_is_complete


def test_bundle_does_not_call_requested_scanners_executed() -> None:
    """O bundle anunciava como executado o que só tinha sido pedido."""
    scan = SimpleNamespace(
        requested_scanners=["semgrep", "gitleaks", "trivy"],
        errors=["trivy: indisponível (health check falhou)"],
    )
    cov = _coverage(scan)
    assert cov["scanners_executed"] == ["semgrep", "gitleaks"]  # trivy NÃO entra
    assert cov["scanners_failed"] == ["trivy"]
    assert cov["coverage_complete"] is False
    assert "NÃO significa alvo limpo" in cov["coverage_note"]


def test_bundle_reports_complete_coverage_when_everything_ran() -> None:
    scan = SimpleNamespace(requested_scanners=["semgrep", "gitleaks"], errors=[])
    cov = _coverage(scan)
    assert cov["scanners_executed"] == ["semgrep", "gitleaks"]
    assert cov["coverage_complete"] is True
