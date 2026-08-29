"""Regressão: o adapter do nuclei quebrava ao receber `templates` como lista.

Bug latente encontrado rodando o pipeline DE VERDADE contra um alvo — ninguém via
porque o nuclei era órfão (fora da fábrica) e nunca era executado.
"""

from __future__ import annotations

import pytest

from orchestrator.adapters.nuclei_adapter import NucleiAdapter
from orchestrator.domain.schemas import AssetType, Target


class _Capture:
    """Captura o argv sem executar nada."""

    def __init__(self) -> None:
        self.argv: list[str] = []

    async def __call__(self, *args, **kwargs):
        self.argv = list(args)
        raise RuntimeError("stop-after-capture")


@pytest.mark.parametrize(
    "templates",
    [["http/exposures/"], ["http/exposures/", "http/misconfiguration/"], "http/cves/"],
)
async def test_templates_become_repeated_t_flags(
    monkeypatch: pytest.MonkeyPatch, templates: object
) -> None:
    cap = _Capture()
    monkeypatch.setattr("asyncio.create_subprocess_exec", cap)
    adapter = NucleiAdapter()
    target = Target(asset_type=AssetType.URL, value="http://127.0.0.1:8088")
    with pytest.raises(RuntimeError, match="stop-after-capture"):
        await adapter.start_scan(target, {"templates": templates})

    # todo argumento tem que ser string — uma lista aqui é o TypeError do subprocess
    assert all(isinstance(a, str) for a in cap.argv), cap.argv
    expected = [templates] if isinstance(templates, str) else templates
    assert cap.argv.count("-t") == len(expected)
    for tpl in expected:
        assert tpl in cap.argv


async def test_nuclei_does_not_hang_on_restricted_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem -duc/-ni o nuclei tenta a internet (update check + interactsh) e PENDURA
    até o timeout do adapter — zero findings que parece "alvo limpo". Reproduzido
    com egress bloqueado: travava; com os flags, terminou em segundos e achou o
    .git exposto."""
    cap = _Capture()
    monkeypatch.setattr("asyncio.create_subprocess_exec", cap)
    target = Target(asset_type=AssetType.URL, value="http://127.0.0.1:8088")
    with pytest.raises(RuntimeError, match="stop-after-capture"):
        await NucleiAdapter().start_scan(target, {})
    assert "-duc" in cap.argv, "update check ligado: pendura sem egress"
    assert "-ni" in cap.argv, "interactsh ligado: pendura sem egress"
