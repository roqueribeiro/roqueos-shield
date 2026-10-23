"""Export para o DefectDojo: o que vai no "Generic Findings Import" e o que não vai.

Até 23/10/2026 o módulo não tinha teste nenhum (0% de cobertura). O que importa
aqui é o contrato com o DefectDojo: severidade no vocabulário dele, a chave de
dedupe como `unique_id_from_tool` (é ela que evita duplicar item a cada reimport),
o token só no header, e recusa explícita quando falta configuração.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from orchestrator.persistence.models import FindingRow, ScanRow, TargetRow
from orchestrator.reporting.exporters import defectdojo


@pytest_asyncio.fixture
async def fabrica(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    fab = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sessao():
        async with fab() as s:
            yield s

    monkeypatch.setattr(defectdojo, "session", sessao)
    monkeypatch.setattr(defectdojo.settings, "DEFECTDOJO_URL", "https://dojo.example/")
    monkeypatch.setattr(defectdojo.settings, "DEFECTDOJO_API_KEY", "tok-123")
    yield fab
    await engine.dispose()


async def _scan_com_dois_achados(fab) -> ScanRow:
    alvo = TargetRow(asset_type="url", value="https://app.example", label="App")
    scan = ScanRow(target_id=alvo.id, created_at=datetime(2026, 10, 23, 12, tzinfo=UTC))
    achados = [
        FindingRow(
            scan_id=scan.id,
            target_id=alvo.id,
            deduped_key="K-xss",
            source_tool="zap",
            source_rule_id="40012",
            title="XSS refletido",
            severity="high",
            confidence="firm",
            vuln_id="CVE-2026-0001",
            payload={"description": "d", "remediation": "escape", "cwe": ["CWE-79"]},
        ),
        FindingRow(
            scan_id=scan.id,
            target_id=alvo.id,
            deduped_key="K-hdr",
            source_tool="nuclei",
            title="Header ausente",
            severity="desconhecida",
            confidence="tentative",
            payload={},
        ),
    ]
    async with fab() as s:
        s.add(alvo)
        s.add(scan)
        for a in achados:
            s.add(a)
        await s.commit()
    return scan


def _capturar(monkeypatch) -> list[httpx.Request]:
    enviadas: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        enviadas.append(request)
        return httpx.Response(201, json={"test": 77})

    original = httpx.AsyncClient

    def cliente(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(responder)
        return original(*args, **kwargs)

    monkeypatch.setattr(defectdojo.httpx, "AsyncClient", cliente)
    return enviadas


async def test_envia_os_achados_no_formato_generico_com_a_chave_de_dedupe(fabrica, monkeypatch):
    scan = await _scan_com_dois_achados(fabrica)
    enviadas = _capturar(monkeypatch)

    resposta = await defectdojo.export_scan(scan.id, engagement_id=9)

    assert resposta == {"test": 77}
    [req] = enviadas
    assert str(req.url) == "https://dojo.example/api/v2/import-scan/"
    assert req.headers["Authorization"] == "Token tok-123"
    corpo = req.content.decode("utf-8", "replace")
    for campo, valor in {
        "scan_type": "Generic Findings Import",
        "scan_date": "2026-10-23",
        "engagement": "9",
        "service": "App",
    }.items():
        assert f'name="{campo}"\r\n\r\n{valor}\r\n' in corpo
    arquivo = corpo.split('filename="')[1].split("\r\n\r\n", 1)[1].split("\r\n--")[0]
    achados = {f["unique_id_from_tool"]: f for f in json.loads(arquivo)["findings"]}
    assert achados["K-xss"] == {
        "title": "XSS refletido",
        "severity": "High",
        "description": "d",
        "mitigation": "escape",
        "vuln_id_from_tool": "40012",
        "cve": "CVE-2026-0001",
        "cwe": "CWE-79",
        "tags": ["zap", "firm"],
        "unique_id_from_tool": "K-xss",
    }
    # severidade fora do vocabulário vira Info, nunca some
    assert achados["K-hdr"]["severity"] == "Info"
    assert achados["K-hdr"]["cwe"] is None
    # o token não vai no corpo, só no header
    assert "tok-123" not in corpo


async def test_sem_configuracao_recusa_antes_de_tocar_no_banco(fabrica, monkeypatch):
    monkeypatch.setattr(defectdojo.settings, "DEFECTDOJO_API_KEY", "")
    with pytest.raises(RuntimeError, match="DEFECTDOJO_URL/API_KEY"):
        await defectdojo.export_scan(uuid4())


async def test_scan_inexistente_e_erro_claro(fabrica):
    with pytest.raises(ValueError, match="não encontrado"):
        await defectdojo.export_scan(uuid4())
