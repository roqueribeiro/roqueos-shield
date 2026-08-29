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


# --- B4: "não achou nada" era "não rodou a ferramenta certa" ---
from orchestrator.jobs.pipelines import _supported_for  # noqa: E402


def test_legacy_default_on_image_falls_back_to_asset_default() -> None:
    # cliente antigo manda ["nmap","zap"] pra uma IMAGE: os dois são incompatíveis,
    # levantavam ValueError e o scan fechava com ZERO findings.
    assert _supported_for(["nmap", "zap"], AssetType.IMAGE) == []


def test_legacy_default_on_repo_falls_back_to_asset_default() -> None:
    assert _supported_for(["nmap", "zap"], AssetType.REPO) == []


def test_supported_keeps_compatible_scanners() -> None:
    assert _supported_for(["trivy", "nmap"], AssetType.IMAGE) == ["trivy"]
    assert _supported_for(["zap", "trivy"], AssetType.URL) == ["zap"]
    assert _supported_for(["semgrep", "gitleaks"], AssetType.REPO) == ["semgrep", "gitleaks"]


def test_port_target_supported_by_nmap() -> None:
    # _DEFAULT_SCANNERS[PORT] == ["nmap"], mas o nmap rejeitava PORT (bug irmão).
    assert _supported_for(["nmap"], AssetType.PORT) == ["nmap"]
    assert _DEFAULT_SCANNERS[AssetType.PORT] == ["nmap"]


# --- profile deixou de ser metadado morto ---
def test_profile_full_enables_zap_active_scan() -> None:
    from orchestrator.api.routers.scans import apply_profile

    assert apply_profile({}, "full")["zap"]["active"] is True
    assert apply_profile({}, "active")["zap"]["active"] is True


def test_profile_web_stays_passive() -> None:
    from orchestrator.api.routers.scans import apply_profile

    assert "zap" not in apply_profile({}, "web")


def test_profile_does_not_override_explicit_option() -> None:
    from orchestrator.api.routers.scans import apply_profile

    assert apply_profile({"zap": {"active": False}}, "full")["zap"]["active"] is False


# --- o profile da UI vira a lista de verdade (contrato com o ROSPentest.vue) ---
def test_web_profile_delivers_what_the_ui_promises() -> None:
    """A UI diz 'Aplicação web (OWASP): nmap + ZAP + Nuclei'. O nuclei era órfão e o
    front não manda `scanners`, então o scan web rodava só ZAP passivo."""
    from orchestrator.jobs.pipelines import resolve_scanners

    assert resolve_scanners(None, AssetType.URL, "web") == ["zap", "nuclei"]


def test_full_profile_runs_all_applicable() -> None:
    from orchestrator.jobs.pipelines import resolve_scanners

    assert resolve_scanners(None, AssetType.URL, "full") == ["nmap", "zap", "nuclei"]
    assert "semgrep" in resolve_scanners(None, AssetType.REPO, "full")


def test_network_profile_is_ports_only() -> None:
    from orchestrator.jobs.pipelines import resolve_scanners

    assert resolve_scanners(None, AssetType.HOST, "network") == ["nmap"]


def test_explicit_scanners_win_over_profile() -> None:
    from orchestrator.jobs.pipelines import resolve_scanners

    assert resolve_scanners(["zap"], AssetType.URL, "full") == ["zap"]


def test_resolved_list_is_never_empty() -> None:
    """O front mostra `scanners_executed`: lista vazia deixaria a tela com '—'."""
    from orchestrator.jobs.pipelines import resolve_scanners

    for at in (AssetType.URL, AssetType.HOST, AssetType.IMAGE, AssetType.REPO, AssetType.PORT):
        assert resolve_scanners(None, at, "web")
        assert resolve_scanners(["nmap", "zap"], at, None)  # cliente antigo, alvo incompatível
