"""Scanner selection by asset type — the wiring that lets IMAGE/REPO scans run
their real tools (trivy/gitleaks/checkov) instead of the old hardcoded [nmap,zap].
"""

from __future__ import annotations

from orchestrator.domain.schemas import AssetType
from orchestrator.jobs.pipelines import _DEFAULT_SCANNERS, _build_adapters


def test_default_scanners_per_asset_type() -> None:
    assert _DEFAULT_SCANNERS[AssetType.IMAGE] == ["trivy"]
    assert _DEFAULT_SCANNERS[AssetType.URL] == ["zap"]
    assert _DEFAULT_SCANNERS[AssetType.HOST] == ["nmap"]
    repo = _DEFAULT_SCANNERS[AssetType.REPO]
    # repo gets the secret + IaC + vuln tools
    assert "gitleaks" in repo
    assert "trufflehog" in repo
    assert "trivy" in repo
    assert "checkov" in repo


def test_build_adapters_resolves_names_in_order() -> None:
    adapters = _build_adapters(["trivy", "gitleaks", "checkov"])
    assert [a.name for a in adapters] == ["trivy", "gitleaks", "checkov"]


def test_build_adapters_skips_unknown_keeps_valid() -> None:
    adapters = _build_adapters(["trivy", "bogus", "zap"])
    names = [a.name for a in adapters]
    assert "bogus" not in names
    assert names == ["trivy", "zap"]


def test_build_adapters_empty_when_all_unknown() -> None:
    assert _build_adapters(["nope", "nada"]) == []


def test_image_default_resolves_to_trivy() -> None:
    adapters = _build_adapters(_DEFAULT_SCANNERS[AssetType.IMAGE])
    assert len(adapters) == 1
    assert adapters[0].name == "trivy"


# --- Onda 1: motores antes órfãos agora construíveis + semgrep no default ---
def test_semgrep_in_repo_default() -> None:
    assert "semgrep" in _DEFAULT_SCANNERS[AssetType.REPO]


def test_nuclei_and_greenbone_now_buildable() -> None:
    # antes caíam em scanner.unknown e sumiam do scan; agora instanciáveis se pedidos.
    adapters = _build_adapters(["nuclei", "greenbone"])
    assert {a.name for a in adapters} == {"nuclei", "greenbone"}
