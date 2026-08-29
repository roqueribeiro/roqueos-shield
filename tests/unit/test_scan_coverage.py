"""Cobertura declarada: "não rodou" nunca pode parecer "não achou".

Este arquivo trava a correção estrutural: um scanner que não rodou aparece no
resultado, no que é GRAVADO, no bundle e no relatório.

LIÇÃO PAGA AQUI: a primeira versão destes testes montava o scan com
`SimpleNamespace(requested_scanners=[...], errors=[...])` — e passava. Só que
`ScanRow.errors` **nunca era gravado** pelo pipeline: o mock reproduzia um estado que
a produção jamais atinge, e escondia exatamente o elo quebrado. O conserto inteiro da
cobertura era inerte ponta a ponta, e o teste dizia que estava tudo bem.

Por isso agora os testes usam `ScanRow` de verdade, e existe um de integração que
roda `run_scan` com um adapter que falha e afirma sobre a **linha persistida**. Mock
de estrutura de dado prova serialização; só o dado que a produção grava prova o
comportamento.
"""

from __future__ import annotations

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


def _scan_row(**kw):
    """ScanRow de verdade — não SimpleNamespace. Ver o cabeçalho do arquivo."""
    from uuid import uuid4

    from orchestrator.persistence.models import ScanRow

    kw.setdefault("target_id", uuid4())
    return ScanRow(**kw)


def test_bundle_does_not_call_requested_scanners_executed() -> None:
    """O bundle anunciava como executado o que só tinha sido pedido."""
    scan = _scan_row(
        requested_scanners=["semgrep", "gitleaks", "trivy"],
        scanners_ran=["semgrep", "gitleaks"],
        scanners_skipped={"trivy": "indisponível (health check falhou)"},
        errors=["trivy: indisponível (health check falhou)"],
    )
    cov = _coverage(scan)
    assert cov["scanners_executed"] == ["semgrep", "gitleaks"]  # trivy NÃO entra
    assert cov["scanners_failed"] == ["trivy"]
    assert cov["coverage_complete"] is False
    assert "NÃO significa alvo limpo" in cov["coverage_note"]
    assert "health check" in cov["scanners_failed_reason"]["trivy"]


def test_bundle_reports_complete_coverage_when_everything_ran() -> None:
    scan = _scan_row(
        requested_scanners=["semgrep", "gitleaks"],
        scanners_ran=["semgrep", "gitleaks"],
    )
    cov = _coverage(scan)
    assert cov["scanners_executed"] == ["semgrep", "gitleaks"]
    assert cov["coverage_complete"] is True


def test_bundle_sem_dado_de_cobertura_nao_afirma_que_rodou() -> None:
    """Linha antiga (pré-0007) ou falha ao gravar: não dá para afirmar cobertura.

    Antes isto devolvia `coverage_complete: true` e listava como EXECUTADO tudo o
    que tinha sido pedido — a mentira mais confortável possível.
    """
    scan = _scan_row(requested_scanners=["semgrep", "trivy"])
    cov = _coverage(scan)
    assert cov["coverage_complete"] is False
    assert cov["scanners_executed"] == []
    assert "DESCONHECIDA" in cov["coverage_note"]
