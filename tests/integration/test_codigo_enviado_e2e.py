"""Código enviado de ponta a ponta, com scanners de verdade.

O teste unitário prova a lógica com scanner falso. Este prova o que importa para quem
manda código para o RoqueShield central: o tarball que a CLI monta, recebido pela API,
extraído e fotografado em git pelo worker, faz o semgrep e o gitleaks reais acharem
os defeitos plantados do gabarito da régua. E o segundo envio do MESMO código tem os
mesmos achados com as mesmas chaves, então o gate aprova (nada novo): sem isso, todo
envio seria "tudo novo" e o gate só serviria para reprovar.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from orchestrator.api import deps
from orchestrator.cliente.empacotar import empacotar
from orchestrator.config import settings
from orchestrator.domain.roles import Role
from orchestrator.jobs import workers
from orchestrator.main import app
from orchestrator.persistence.db import init_db

RAIZ = Path(__file__).resolve().parents[2]
_TEM_SCANNERS = bool(shutil.which("semgrep") and shutil.which("gitleaks"))
# No CI (job da régua de detecção) os scanners estão instalados e o teste NÃO pode pular:
# um skip ali seria a prova de efetividade virando verde sem rodar.
if os.environ.get("ROQUESHIELD_EXIGIR_SCANNERS") == "1" and not _TEM_SCANNERS:
    raise RuntimeError("ROQUESHIELD_EXIGIR_SCANNERS=1 e o semgrep ou o gitleaks não está no PATH")
pytestmark = pytest.mark.skipif(
    not _TEM_SCANNERS, reason="precisa do semgrep e do gitleaks instalados"
)


@pytest_asyncio.fixture(autouse=True)
async def _ambiente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(settings, "REQUIRE_AUTH_REF", False)
    import orchestrator.runtime_settings as rs

    async def _nada(_s: Any) -> list[str]:
        return []

    monkeypatch.setattr(rs, "aplicar", _nada)
    await init_db()
    yield
    app.dependency_overrides.clear()


def _cliente() -> AsyncClient:
    app.dependency_overrides[deps.get_principal] = lambda: deps.Principal(
        id="u1", email="ci@x", role=Role.OPERATOR, is_service=False
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _arvore(destino: Path) -> Path:
    """O repo sintético da régua, com os segredos falsos gerados na hora, SEM git."""
    sys.path.insert(0, str(RAIZ / "scripts"))
    import regua  # type: ignore[import-not-found]

    shutil.copytree(regua.FIXTURE, destino)
    for rel, conteudo in regua._segredos_de_teste().items():
        (destino / rel).parent.mkdir(parents=True, exist_ok=True)
        (destino / rel).write_text(conteudo, encoding="utf-8")
    return destino


async def _enviar_e_escanear(c: AsyncClient, pacote: bytes) -> str:
    r = await c.post(
        "/code/regua/uploads", content=pacote, headers={"Content-Type": "application/gzip"}
    )
    assert r.status_code == 201, r.text
    envio = r.json()
    res = await workers.run_scan_job(
        {},
        target_value=envio["target_value"],
        asset_type="repo",
        scanners=["semgrep", "gitleaks"],
        code_upload_id=envio["upload_id"],
    )
    return str(res["scan_id"])


async def test_envio_real_acha_os_defeitos_e_o_reenvio_nao_tem_nada_novo(
    tmp_path: Path,
) -> None:
    arvore = _arvore(tmp_path / "projeto")
    pacote = empacotar(arvore).dados
    async with _cliente() as c:
        primeiro = await _enviar_e_escanear(c, pacote)
        g1 = (await c.get(f"/scans/{primeiro}/gate", params={"fail_on": "high"})).json()
        achados = (await c.get("/findings", params={"scan_id": primeiro, "limit": 500})).json()

        segundo = await _enviar_e_escanear(c, pacote)
        g2 = (await c.get(f"/scans/{segundo}/gate", params={"fail_on": "high"})).json()

    ferramentas = {a["source_tool"] for a in achados}
    # As duas camadas acharam de verdade, pelo envio.
    assert "semgrep" in ferramentas, ferramentas
    assert "gitleaks" in ferramentas, ferramentas
    assert g1["coverage_complete"] is True
    assert g1["verdict"] == "reprovado", g1
    assert g1["baseline_scan_id"] is None
    # O mesmo código de novo: mesmas chaves, nada novo, gate aprova.
    assert g2["baseline_scan_id"] == primeiro
    assert g2["novos"] == 0, g2
    assert g2["verdict"] == "aprovado", g2
    # E o código não ficou no disco do scanner.
    assert list((Path(settings.DATA_DIR) / "code").glob("*.tar.gz")) == []
