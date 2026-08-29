"""Checkov: zero achados só pode significar "IaC sem problema", nunca "não rodou".

O bug original era o pior tipo de silêncio: `start_scan` passava a URL do repo para
`checkov -d`. O checkov loga "Directory does not exist; skipping it", sai com código
0 e escreve saída VAZIA — e o adapter transformava isso em `{}` → zero findings →
"IaC limpo". Todo scan de REPO com alvo-URL passou por esse caminho.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest

from orchestrator.adapters.base import ScanIntegrityError
from orchestrator.adapters.checkov_adapter import CheckovAdapter
from orchestrator.domain.schemas import AssetType, ScanHandle, ScanStatus, Target

TERRAFORM_INSEGURO = """
resource "aws_s3_bucket" "b" {
  bucket = "bucket-de-teste-do-adapter"
  acl    = "public-read"
}
"""


def _handle(nid: str) -> ScanHandle:
    return ScanHandle(adapter="checkov", native_id=nid, metadata={})


def _plant(ad: CheckovAdapter, payload: str | None, rc: int = 0) -> ScanHandle:
    """Monta um handle com saída já escrita, sem rodar o binário."""
    import tempfile

    nid = str(uuid4())
    wd = Path(tempfile.mkdtemp(prefix="cai-checkov-test-"))
    out = wd / "out.json"
    if payload is not None:
        out.write_text(payload, encoding="utf-8")
    ad._workdirs[nid] = wd

    async def _done() -> tuple[int, Path]:
        return rc, out

    ad._tasks[nid] = asyncio.get_event_loop().create_task(_done())
    return _handle(nid)


# --------------------------------------------------------------- integridade


@pytest.mark.asyncio
async def test_saida_vazia_nao_e_alvo_limpo() -> None:
    """O caso exato do bug: checkov sai 0 e não escreve nada."""
    ad = CheckovAdapter()
    h = _plant(ad, payload="")
    await asyncio.sleep(0)
    with pytest.raises(ScanIntegrityError, match="VAZIA"):
        await ad.fetch_results(h)


@pytest.mark.asyncio
async def test_arquivo_ausente_nao_e_alvo_limpo() -> None:
    ad = CheckovAdapter()
    h = _plant(ad, payload=None)
    await asyncio.sleep(0)
    with pytest.raises(ScanIntegrityError, match="não escreveu"):
        await ad.fetch_results(h)


@pytest.mark.asyncio
async def test_json_corrompido_nao_e_alvo_limpo() -> None:
    ad = CheckovAdapter()
    h = _plant(ad, payload="{ isto nao e json")
    await asyncio.sleep(0)
    with pytest.raises(ScanIntegrityError, match="não é JSON"):
        await ad.fetch_results(h)


@pytest.mark.asyncio
async def test_so_parsing_error_sem_avaliacao_reprova() -> None:
    """Nada avaliado + arquivos que não parsearam = cobertura zero."""
    ad = CheckovAdapter()
    payload = json.dumps(
        {"passed": 0, "failed": 0, "skipped": 0, "parsing_errors": 3, "resource_count": 0}
    )
    h = _plant(ad, payload=payload)
    await asyncio.sleep(0)
    with pytest.raises(ScanIntegrityError, match="NENHUM controle"):
        await ad.fetch_results(h)


@pytest.mark.asyncio
async def test_repo_sem_iac_e_resultado_legitimo() -> None:
    """Repo sem nenhum arquivo IaC: zero achados é honesto, não deve levantar."""
    ad = CheckovAdapter()
    payload = json.dumps(
        {"passed": 0, "failed": 0, "skipped": 0, "parsing_errors": 0, "resource_count": 0}
    )
    h = _plant(ad, payload=payload)
    await asyncio.sleep(0)
    raw = await ad.fetch_results(h)
    assert await ad.normalize(raw) == []


@pytest.mark.asyncio
async def test_parsing_error_parcial_vira_achado_visivel() -> None:
    """Parte avaliada + parte não: mantém os achados E denuncia a lacuna."""
    ad = CheckovAdapter()
    payload = json.dumps(
        {
            "check_type": "terraform",
            "results": {"failed_checks": []},
            "summary": {
                "passed": 10,
                "failed": 0,
                "skipped": 0,
                "parsing_errors": 2,
                "resource_count": 4,
            },
        }
    )
    h = _plant(ad, payload=payload)
    await asyncio.sleep(0)
    raw = await ad.fetch_results(h)
    findings = await ad.normalize(raw)
    assert [f.source_rule_id for f in findings] == ["checkov-parsing-errors"]
    assert "NÃO foram avaliados" in findings[0].description


# ------------------------------------------------------------------- poll


@pytest.mark.asyncio
async def test_poll_reprova_quando_o_processo_falhou() -> None:
    """Antes: `task.done()` bastava para DONE — clone falho fechava como concluído."""
    ad = CheckovAdapter()
    h = _plant(ad, payload="", rc=128)  # 128 = git clone falhou
    await asyncio.sleep(0)
    assert await ad.poll(h) == ScanStatus.FAILED


@pytest.mark.asyncio
async def test_poll_ok_quando_rodou() -> None:
    ad = CheckovAdapter()
    h = _plant(ad, payload="{}", rc=0)
    await asyncio.sleep(0)
    assert await ad.poll(h) == ScanStatus.DONE


@pytest.mark.asyncio
async def test_alvo_incompativel_e_recusado() -> None:
    ad = CheckovAdapter()
    with pytest.raises(ValueError, match="só suporta REPO"):
        await ad.start_scan(Target(asset_type=AssetType.URL, value="http://x.test"), {})


# ---------------------------------------------------------- e2e com binário

pytestmark_bin = pytest.mark.skipif(
    CheckovAdapter().bin == "checkov" and __import__("shutil").which("checkov") is None,
    reason="binário do checkov ausente",
)


@pytestmark_bin
@pytest.mark.asyncio
async def test_e2e_diretorio_local_com_terraform_inseguro(tmp_path: Path) -> None:
    """Prova que o caminho feliz acha de verdade — senão os testes acima passariam
    numa ferramenta que nunca acha nada."""
    (tmp_path / "main.tf").write_text(TERRAFORM_INSEGURO, encoding="utf-8")
    ad = CheckovAdapter()
    if not await ad.health():
        pytest.skip("checkov não responde --version")

    alvo = Target(asset_type=AssetType.REPO, value=str(tmp_path))
    h = await ad.start_scan(alvo, {"framework": "terraform"})
    for _ in range(120):
        st = await ad.poll(h)
        if st != ScanStatus.RUNNING:
            break
        await asyncio.sleep(1)
    assert st == ScanStatus.DONE
    raw = await ad.fetch_results(h)
    findings = await ad.normalize(raw)
    await ad.cleanup(h)
    assert findings, "checkov não achou nada num bucket S3 public-read"
    assert any("CKV_AWS" in (f.source_rule_id or "") for f in findings)


@pytestmark_bin
@pytest.mark.asyncio
async def test_e2e_alvo_url_nao_fecha_como_limpo() -> None:
    """A regressão do bug original: URL inalcançável NÃO pode virar 'IaC limpo'."""
    ad = CheckovAdapter()
    if not await ad.health():
        pytest.skip("checkov não responde --version")

    alvo = Target(
        asset_type=AssetType.REPO,
        value="https://127.0.0.1:1/repo-que-nao-existe.git",
    )
    h = await ad.start_scan(alvo, {})
    for _ in range(60):
        st = await ad.poll(h)
        if st != ScanStatus.RUNNING:
            break
        await asyncio.sleep(1)
    await ad.cleanup(h)
    assert st == ScanStatus.FAILED, "clone impossível tem que reprovar, não fechar limpo"
