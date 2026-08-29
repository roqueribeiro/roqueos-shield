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


def test_usa_o_diretorio_embarcado_quando_existe(tmp_path, monkeypatch) -> None:
    """Sem templates o nuclei sai com "no templates provided" e rc 1.

    Honesto (vira `scanners_skipped`), mas inútil em 100% dos scans "web" e "full" —
    que são justamente os que a UI do RoqueShield promete com nuclei. A imagem passa
    a embarcar os templates, e o adapter os usa por padrão.
    """
    from orchestrator.adapters.nuclei_adapter import NucleiAdapter

    monkeypatch.setenv("NUCLEI_TEMPLATES_DIR", str(tmp_path))
    assert NucleiAdapter().templates_dir == str(tmp_path)


def test_sem_diretorio_embarcado_deixa_o_nuclei_decidir(tmp_path, monkeypatch) -> None:
    from orchestrator.adapters.nuclei_adapter import NucleiAdapter

    monkeypatch.setenv("NUCLEI_TEMPLATES_DIR", str(tmp_path / "nao-existe"))
    assert NucleiAdapter().templates_dir is None


def test_dockerfile_confere_a_contagem_de_templates() -> None:
    """`nuclei -update-templates` falha com um WRN e devolve **rc 0**.

    Medido nesta máquina, com o proxy recusando o repo: warning, exit 0, zero
    templates. Um `RUN` ingênuo (ou com `|| true`, que era o caso do kali) geraria
    imagem verde e vazia — o mesmo silêncio, agora no build.
    """
    from pathlib import Path

    for arquivo in (
        "docker/images/orchestrator/Dockerfile",
        "docker/images/kali-toolbox/Dockerfile",
    ):
        fonte = Path(arquivo).read_text(encoding="utf-8")
        assert "NUCLEI_TEMPLATES_MIN" in fonte, f"{arquivo} sem piso de templates"
        assert "nuclei -tl" in fonte, f"{arquivo} não conta o que baixou"
        assert "-update-templates || true" not in fonte, f"{arquivo} ainda engole a falha"
