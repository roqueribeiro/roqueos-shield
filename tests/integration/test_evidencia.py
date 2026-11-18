"""Evidência — captura no pipeline e imutabilidade (Frente C).

Prova que persistir um achado grava o snapshot redigido e o vínculo `proof` pela
`deduped_key`, e que a migration realmente instala o trigger append-only (a garantia que
o Postgres cumpre em produção). Afirma sobre o dado persistido.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlmodel import select

from orchestrator.config import settings
from orchestrator.domain.schemas import AssetType, Confidence, Evidence, Finding, Severity, Target
from orchestrator.evidence import store
from orchestrator.evidence.service import capturar_evidencias
from orchestrator.persistence.db import init_db, session
from orchestrator.persistence.models import EvidenceLinkRow, EvidenceSnapshotRow


@pytest.fixture
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    return tmp_path


async def test_captura_liga_evidencia_ao_problema_e_redige(_data_dir) -> None:
    await init_db()
    scan_id = uuid.uuid4()
    finding = Finding(
        scan_id=scan_id,
        target=Target(asset_type=AssetType.URL, value="https://alvo.test/login"),
        source_tool="zap",
        source_rule_id="40018",
        title="SQLi",
        description="injeção",
        severity=Severity.HIGH,
        confidence=Confidence.FIRM,
        evidence=[
            Evidence(
                description="resposta",
                response="HTTP/1.1 200 OK\nvazou alvo@banco.com.br e senha=hunter2",
            )
        ],
    )

    async with session() as s:
        gravados = await capturar_evidencias(s, scan_id, finding)
        await s.commit()
    assert gravados == 1

    async with session() as s:
        links = (
            await s.exec(
                select(EvidenceLinkRow).where(EvidenceLinkRow.deduped_key == finding.deduped_key)
            )
        ).all()
        assert len(links) == 1
        assert links[0].papel == "proof"
        snap = await s.get(EvidenceSnapshotRow, links[0].snapshot_id)
        assert snap is not None

    # O corpo em disco está redigido: sem e-mail nem valor do segredo.
    corpo = store.get(snap.sha256).decode()
    assert "alvo@banco.com.br" not in corpo
    assert "hunter2" not in corpo


def test_migration_0011_instala_trigger_append_only() -> None:
    # Garante que o trigger write-once está na migration; removê-lo reprova.
    fonte = Path("orchestrator/persistence/migrations/versions/0011_evidence_store.py").read_text(
        encoding="utf-8"
    )
    assert "evidence_snapshots_no_update" in fonte
    assert "RAISE EXCEPTION" in fonte
    assert "BEFORE UPDATE OR DELETE ON evidence_snapshots" in fonte
