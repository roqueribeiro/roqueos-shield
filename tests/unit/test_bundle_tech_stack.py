"""O Fix Bundle mandava tech_stack_hints TODO vazio — a IA de patch não sabia nem a
linguagem nem onde estava o código. Agora deriva das evidências dos scanners."""

from __future__ import annotations

from types import SimpleNamespace

from orchestrator.reporting.exporters.ai_bundle import derive_tech_stack


def _f(tool: str, value: str, description: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        source_tool=tool,
        payload={"target": {"value": value}, "description": description},
    )


def test_derives_language_from_source_path() -> None:
    st = derive_tech_stack([_f("semgrep", "app/handler.py:12")])
    assert "python" in st["languages"]
    assert st["confidence"] == "medium"


def test_derives_package_manager_from_manifest() -> None:
    st = derive_tech_stack([_f("trivy", "requirements.txt"), _f("trivy", "package.json")])
    assert {"pip", "npm"} <= set(st["package_managers"])


def test_derives_server_from_nmap_banner() -> None:
    st = derive_tech_stack([_f("nmap", "1.2.3.4:80/tcp", "Serviço detectado: nginx 1.18")])
    assert "nginx" in st["servers"]


def test_repo_target_marks_source_available() -> None:
    from orchestrator.reporting.exporters.ai_bundle import _target_section

    target = SimpleNamespace(
        value="https://github.com/x/y", asset_type="repo", label=None, contains_pii=False
    )
    sec = _target_section(target, [_f("semgrep", "src/main.go:9")])
    assert sec["source_code_available_to_patcher"] is True
    assert "go" in sec["tech_stack_hints"]["languages"]
    assert "https://github.com/x/y" in sec["tech_stack_hints"]["source_repos"]


def test_empty_findings_stay_low_confidence() -> None:
    st = derive_tech_stack([])
    assert st["confidence"] == "low" and st["languages"] == []
