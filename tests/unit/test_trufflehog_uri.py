"""Regressão: trufflehog `git` exige URI, caminho local cru morre calado.

Medido ao vivo em 2026-11-06 num scan de REPO de caminho local:

    $ trufflehog git /tmp/vulnrepo --json
    error: "failed to scan Git: error preparing repo: unsupported Git URI: /tmp/vulnrepo" (rc=1)
    $ trufflehog git file:///tmp/vulnrepo --json
    finished scanning (rc=0)

O adapter montava `trufflehog git <target.value>` com o caminho cru, o processo
saía 1, o contrato do silêncio marcava `scanners_skipped=['trufflehog']` e o vetor
de secret verificado nunca rodava em repo local. O conserto normaliza caminho local
para `file://<abspath>`; alvo remoto passa intacto.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from orchestrator.adapters.trufflehog_adapter import TrufflehogAdapter, _to_git_uri
from orchestrator.domain.schemas import AssetType, Target


def test_caminho_local_vira_file_uri(tmp_path: Path) -> None:
    uri = _to_git_uri(str(tmp_path))
    # Mutação: reverter o conserto (devolver o valor cru) deixa isto vermelho,
    # porque o caminho local NÃO começa com file://.
    assert uri.startswith("file://"), f"caminho local tem que virar URI, veio {uri!r}"
    assert uri == tmp_path.resolve().as_uri()


def test_caminho_relativo_vira_absoluto_file_uri() -> None:
    uri = _to_git_uri("repo-local")
    assert uri.startswith("file://")
    assert Path("repo-local").resolve().as_uri() == uri


@pytest.mark.parametrize(
    "remoto",
    [
        "https://github.com/org/repo",
        "http://git.interno/org/repo.git",
        "git@github.com:org/repo.git",
        "ssh://git@host/org/repo.git",
        "git://host/org/repo.git",
        "file:///ja/eh/uri",
    ],
)
def test_alvo_remoto_passa_intacto(remoto: str) -> None:
    assert _to_git_uri(remoto) == remoto


def test_start_scan_nao_passa_caminho_cru_pro_trufflehog(tmp_path: Path, monkeypatch) -> None:
    """O comando real que vai pro trufflehog não pode conter o caminho cru."""
    capturado: dict[str, list[str]] = {}

    class _FakeProc:
        returncode = 0

        async def communicate(self):  # noqa: ANN202
            return (b"", b"")

    async def _fake_exec(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        capturado["cmd"] = list(args)
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    ad = TrufflehogAdapter(bin_path="trufflehog")
    alvo = Target(asset_type=AssetType.REPO, value=str(tmp_path))

    async def _exercita() -> None:
        handle = await ad.start_scan(alvo, {})
        # deixa a task interna rodar até o fim no MESMO loop pra não vazar
        await ad._tasks[handle.native_id]

    asyncio.run(_exercita())

    cmd = capturado["cmd"]
    assert cmd[:2] == ["trufflehog", "git"]
    ref = cmd[2]
    assert ref.startswith("file://"), f"trufflehog recebeu caminho cru: {ref!r}"
    assert str(tmp_path) != ref, "o caminho cru foi passado sem virar URI"
    # egress fechado por padrão (regra 60): sem --no-update o updater falha e o
    # scan morre calado numa rede restrita. Mutação: remover a flag deixa vermelho.
    assert "--no-update" in cmd, "trufflehog sem --no-update falha o scan em rede restrita"
