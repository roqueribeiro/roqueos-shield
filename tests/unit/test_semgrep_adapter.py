"""Semgrep adapter — SAST de código-fonte. Objetivo 'qualidade de código' (antes: 0)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from orchestrator.adapters.semgrep_adapter import SemgrepAdapter, _extract_cwes
from orchestrator.domain.schemas import AssetType, RawResults, ScanStatus, Severity, Target


def test_extract_cwes_from_str_and_list() -> None:
    assert _extract_cwes("CWE-89: SQL Injection") == ["CWE-89"]
    assert _extract_cwes(["CWE-79: XSS", "CWE-89: SQLi"]) == ["CWE-79", "CWE-89"]
    assert _extract_cwes(None) == []


async def test_normalize_maps_semgrep_json() -> None:
    payload = {
        "results": [
            {
                "check_id": "python.lang.security.audit.eval-detected.eval-detected",
                "path": "app/handler.py",
                "start": {"line": 12},
                "extra": {
                    "message": "Detected eval() on user input. This can lead to RCE.",
                    "severity": "ERROR",
                    "lines": "    eval(request.args['q'])",
                    "metadata": {
                        "cwe": ["CWE-95: Eval Injection"],
                        "owasp": ["A03:2021 - Injection"],
                        "confidence": "HIGH",
                    },
                },
            }
        ]
    }
    findings = await SemgrepAdapter().normalize(RawResults(adapter="semgrep", payload=payload))
    assert len(findings) == 1
    f = findings[0]
    assert f.source_tool == "semgrep"
    assert f.severity == Severity.HIGH
    assert f.cwe == ["CWE-95"]
    assert f.target.value == "app/handler.py:12"
    assert "eval" in (f.evidence[0].snippet or "")


@pytest.mark.skipif(shutil.which("semgrep") is None, reason="semgrep não instalado")
async def test_semgrep_scans_real_vulnerable_code(tmp_path: Path) -> None:
    (tmp_path / "vuln.py").write_text("def h(x):\n    return eval(x)\n", encoding="utf-8")
    (tmp_path / "rules.yaml").write_text(
        "rules:\n"
        "  - id: no-eval\n"
        "    pattern: eval(...)\n"
        "    message: eval() e perigoso (RCE)\n"
        "    languages: [python]\n"
        "    severity: ERROR\n"
        "    metadata:\n"
        "      cwe: ['CWE-95: Eval Injection']\n",
        encoding="utf-8",
    )
    adapter = SemgrepAdapter()
    assert await adapter.health()
    target = Target(asset_type=AssetType.REPO, value=str(tmp_path))
    handle = await adapter.start_scan(target, {"config": str(tmp_path / "rules.yaml")})
    st = ScanStatus.RUNNING
    for _ in range(60):
        st = await adapter.poll(handle)
        if st != ScanStatus.RUNNING:
            break
        await asyncio.sleep(1)
    assert st == ScanStatus.DONE
    findings = await adapter.normalize(await adapter.fetch_results(handle))
    await adapter.cleanup(handle)
    assert any(f.source_tool == "semgrep" and "CWE-95" in f.cwe for f in findings)
    assert any(f.target.value.endswith(":2") for f in findings)  # eval está na linha 2


# --- integridade: zero achados só vale se alguma regra rodou ---
def test_zero_rules_is_not_clean_code() -> None:
    """Config que não resolve (registry sem egress, pack privado, caminho errado)
    faz o semgrep sair com código 0, zero regras e zero achados — indistinguível de
    código são. Reproduzido com `rules: []`: exit 0 / 0 regras / 0 resultados."""
    from orchestrator.adapters.semgrep_adapter import _rules_ran

    assert _rules_ran({"time": {"rules": []}, "results": []}) == 0
    assert _rules_ran({"results": []}) == 0
    assert _rules_ran({}) == 0
    assert _rules_ran({"time": {"rules": ["a", "b", "c"]}}) == 3


async def test_fetch_results_refuses_a_scan_with_no_rules(tmp_path: Path) -> None:
    from orchestrator.adapters.semgrep_adapter import ScanIntegrityError

    adapter = SemgrepAdapter()
    report = tmp_path / "report.json"
    report.write_text('{"results": [], "time": {"rules": []}}', encoding="utf-8")

    class _Done:
        def result(self):
            return 0, report

    adapter._tasks["x"] = _Done()  # type: ignore[assignment]
    handle = type("H", (), {"native_id": "x"})()
    with pytest.raises(ScanIntegrityError, match="NENHUMA regra"):
        await adapter.fetch_results(handle)  # type: ignore[arg-type]


async def test_fetch_results_accepts_a_scan_that_ran_rules(tmp_path: Path) -> None:
    adapter = SemgrepAdapter()
    report = tmp_path / "report.json"
    report.write_text('{"results": [], "time": {"rules": ["r1", "r2"]}}', encoding="utf-8")

    class _Done:
        def result(self):
            return 0, report

    adapter._tasks["y"] = _Done()  # type: ignore[assignment]
    handle = type("H", (), {"native_id": "y"})()
    raw = await adapter.fetch_results(handle)  # type: ignore[arg-type]
    assert raw.payload["results"] == []  # limpo DE VERDADE: 2 regras rodaram
