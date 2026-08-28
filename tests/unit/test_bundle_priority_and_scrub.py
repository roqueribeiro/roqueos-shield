"""Triagem da IA guiando o handoff, e scrub na investigação.

- Fix Bundle: finding marcado como provável falso positivo não pode ir pro topo da
  fila do patcher (a severity já era a ajustada; o que faltava era este lado).
- cai_expert: o prompt de investigação mandava title/payload CRUS pro LLM — a
  triagem scrubba, a investigação não. Vazamento se cair no fallback cloud.
"""

from __future__ import annotations

import inspect

from orchestrator.reporting.exporters.ai_bundle import _patch_priority


def test_critical_stays_urgent() -> None:
    assert _patch_priority(0, "certain", {}) == 1


def test_likely_false_positive_goes_last() -> None:
    assert _patch_priority(0, "certain", {"is_likely_false_positive": True}) == 5


def test_tentative_still_demotes_one_step() -> None:
    assert _patch_priority(1, "tentative", {}) == 3


def test_no_triage_behaves_as_before() -> None:
    assert _patch_priority(2, "firm", None) == 3


def test_investigation_prompt_scrubs_title_and_payload() -> None:
    from orchestrator.ai.agentic import cai_expert

    src = inspect.getsource(cai_expert._investigate_fallback)
    assert "scrub(finding.title)" in src
    assert "scrub_dict(finding.payload" in src
    assert "{finding.payload}" not in src  # payload cru não vai mais pro LLM
