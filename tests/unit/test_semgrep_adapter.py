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


# ---------------------------------------------------- ruleset offline (banco)


def test_config_auto_e_recusado_com_motivo() -> None:
    """`--config auto` exige telemetria; este projeto roda `--metrics off`.

    A combinação sai com erro e ZERO regras — e era o DEFAULT. O único scanner que
    lê o código falhava em 100% das execuções.
    """
    from orchestrator.adapters.semgrep_adapter import _resolver_configs

    with pytest.raises(ValueError, match="metrics off"):
        _resolver_configs("auto")
    with pytest.raises(ValueError, match="metrics off"):
        _resolver_configs(["p/secrets", "AUTO"])


def test_sem_ruleset_local_cai_nos_packs_do_registry(monkeypatch, tmp_path) -> None:
    from orchestrator.adapters import semgrep_adapter as mod

    monkeypatch.setenv("SEMGREP_RULES_DIR", str(tmp_path / "nao_existe"))
    assert mod._resolver_configs(None) == list(mod._DEFAULT_CONFIGS)


def test_ruleset_local_tem_preferencia_sobre_o_registry(monkeypatch, tmp_path) -> None:
    """Num banco a rede é restrita: `p/...` não alcança o registry e o semgrep sai
    com código 0 e zero regras. O ruleset em disco é o que faz o SAST existir lá."""
    from orchestrator.adapters import semgrep_adapter as mod

    for ling in ("python", "generic", "terraform", "java"):
        (tmp_path / ling).mkdir()
    monkeypatch.setenv("SEMGREP_RULES_DIR", str(tmp_path))

    configs = mod._resolver_configs(None)
    assert configs, "ruleset local existe e foi ignorado"
    assert all(c.startswith(str(tmp_path)) for c in configs)
    assert not any(c.startswith("p/") for c in configs)


def test_seleciona_regras_pela_linguagem_do_checkout(monkeypatch, tmp_path) -> None:
    """Repo Python não paga o parsing das regras de Kotlin.

    Carregar as ~1900 regras de todas as linguagens custa ~2min por scan; pelas
    extensões presentes cai para ~1min sem perder cobertura (regra de linguagem
    ausente não acharia nada mesmo).
    """
    from orchestrator.adapters import semgrep_adapter as mod

    regras = tmp_path / "regras"
    for ling in ("python", "generic", "terraform", "java", "kotlin"):
        (regras / ling).mkdir(parents=True)
    monkeypatch.setenv("SEMGREP_RULES_DIR", str(regras))

    alvo = tmp_path / "repo"
    (alvo / "src").mkdir(parents=True)
    (alvo / "src" / "app.py").write_text("x = 1", encoding="utf-8")
    (alvo / "infra.tf").write_text('resource "x" "y" {}', encoding="utf-8")

    escolhidas = {c.rsplit("/", 1)[-1] for c in mod._resolver_configs(None, alvo)}
    assert escolhidas == {"python", "terraform", "generic"}, escolhidas
    assert "java" not in escolhidas and "kotlin" not in escolhidas


def test_dockerfile_sem_extensao_e_reconhecido(monkeypatch, tmp_path) -> None:
    from orchestrator.adapters import semgrep_adapter as mod

    regras = tmp_path / "regras"
    for ling in ("dockerfile", "generic"):
        (regras / ling).mkdir(parents=True)
    monkeypatch.setenv("SEMGREP_RULES_DIR", str(regras))
    alvo = tmp_path / "repo"
    alvo.mkdir()
    (alvo / "Dockerfile").write_text("FROM debian", encoding="utf-8")
    escolhidas = {c.rsplit("/", 1)[-1] for c in mod._resolver_configs(None, alvo)}
    assert "dockerfile" in escolhidas
