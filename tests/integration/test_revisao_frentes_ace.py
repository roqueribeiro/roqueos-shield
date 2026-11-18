"""Consertos da revisão completa das Frentes A, C e E (auditoria de segurança + correção).

Cada teste trava um defeito confirmado por leitura ou execução; reverter o conserto
reprova. Os que dependem de Postgres de verdade estão em tests/postgres/.
"""

from __future__ import annotations

import hashlib
import io
import os
import time
import uuid
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select

from orchestrator.api import deps
from orchestrator.config import Settings, insecure_boot_errors, settings
from orchestrator.domain.assets import (
    asset_key,
    cobertura_do_tipo,
    registrar_ativos,
    scanner_viu_o_tipo,
)
from orchestrator.domain.roles import Role
from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Evidence,
    Finding,
    Severity,
    Target,
)
from orchestrator.evidence import store
from orchestrator.main import app
from orchestrator.persistence.db import init_db, session
from orchestrator.persistence.models import (
    AssetObservationRow,
    AssetRow,
    AuditLogRow,
    CommandApprovalRow,
    EvidenceSnapshotRow,
    FindingRow,
    ScanRow,
    ScanState,
    TargetRow,
)


@pytest.fixture
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
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


def _finding(scan_id: uuid.UUID, valor: str, *, evidencia: str | None = "corpo") -> Finding:
    return Finding(
        scan_id=scan_id,
        target=Target(asset_type=AssetType.PORT, value=valor, label="http"),
        source_tool="nmap",
        source_rule_id=f"r-{valor}",
        title=f"Open {valor}",
        description="aberta",
        severity=Severity.INFO,
        confidence=Confidence.CERTAIN,
        evidence=[Evidence(description="banner", snippet=evidencia)] if evidencia else [],
    )


# ===================================================== pipeline: não perder findings


async def _persistir(alvo: Target, findings: list[Finding], *, rodaram: list[str]) -> uuid.UUID:
    from orchestrator.jobs.pipelines import ScanResult, _persist_findings

    scan_id = uuid.uuid4()
    for f in findings:
        f.scan_id = scan_id
    resultado = ScanResult(scan_id=scan_id, target=alvo, findings=findings)
    resultado.scanners_ran = list(rodaram)
    await _persist_findings(scan_id, alvo, findings, resultado)
    return scan_id


async def _quebrar_no_banco(sessao, *_args, **_kwargs) -> None:
    # Erro de BANCO de verdade (NOT NULL violado): é o caso que invalida a sessão inteira.
    sessao.add(EvidenceSnapshotRow(sha256=None, original_sha256="x"))  # type: ignore[arg-type]
    await sessao.flush()


async def test_falha_de_banco_na_evidencia_nao_apaga_os_findings(monkeypatch, _data_dir) -> None:
    import orchestrator.evidence.service as ev

    await init_db()
    monkeypatch.setattr(ev, "capturar_evidencias", _quebrar_no_banco)
    alvo = Target(asset_type=AssetType.HOST, value=f"ev-{uuid.uuid4().hex[:6]}.test")
    fs = [_finding(uuid.uuid4(), f"{alvo.value}:{p}/tcp") for p in (80, 443)]
    scan_id = await _persistir(alvo, fs, rodaram=["nmap"])

    async with session() as s:
        gravados = (
            await s.exec(select(FindingRow).where(col(FindingRow.scan_id) == scan_id))
        ).all()
        scan = await s.get(ScanRow, scan_id)
    assert len(gravados) == 2, "a falha da evidência apagou os findings do scan"
    assert scan is not None and scan.state == ScanState.DONE.value
    assert any("evidência não capturada para 2 de 2" in e for e in scan.errors), scan.errors


async def test_falha_de_banco_no_inventario_nao_apaga_os_findings(monkeypatch, _data_dir) -> None:
    import orchestrator.domain.assets as at

    await init_db()
    monkeypatch.setattr(at, "registrar_ativos", _quebrar_no_banco)
    alvo = Target(asset_type=AssetType.HOST, value=f"inv-{uuid.uuid4().hex[:6]}.test")
    scan_id = await _persistir(
        alvo, [_finding(uuid.uuid4(), f"{alvo.value}:22/tcp")], rodaram=["nmap"]
    )

    async with session() as s:
        gravados = (
            await s.exec(select(FindingRow).where(col(FindingRow.scan_id) == scan_id))
        ).all()
        scan = await s.get(ScanRow, scan_id)
    assert len(gravados) == 1
    assert gravados[0].asset_id is None  # o savepoint desfez o ativo: não aponta para o nada
    assert scan is not None and any("inventário de ativos não registrado" in e for e in scan.errors)


# ============================================ inventário: silêncio, scrub, cobertura


async def test_alvo_nao_vira_visto_quando_ninguem_que_o_enxerga_rodou(_data_dir) -> None:
    await init_db()
    host = f"mudo-{uuid.uuid4().hex[:6]}.test"
    alvo = Target(asset_type=AssetType.HOST, value=host)
    scan_id = uuid.uuid4()
    async with session() as s:
        await registrar_ativos(s, scan_id, alvo, [], scanners_ran=[])
        await s.commit()
    async with session() as s:
        ativo = (
            await s.exec(select(AssetRow).where(col(AssetRow.asset_key) == asset_key("host", host)))
        ).first()
        obs = (
            await s.exec(
                select(AssetObservationRow).where(col(AssetObservationRow.scan_id) == scan_id)
            )
        ).all()
    assert ativo is None, "nmap não rodou e o host foi marcado como visto agora"
    assert obs == []


async def test_valor_do_ativo_passa_pelo_scrubber(_data_dir) -> None:
    await init_db()
    scan_id = uuid.uuid4()
    url = f"https://app-{uuid.uuid4().hex[:6]}.test/x?email=alvo@banco.com.br&cpf=529.982.247-25"
    f = Finding(
        scan_id=scan_id,
        target=Target(asset_type=AssetType.URL, value=url),
        source_tool="zap",
        title="XSS",
        description="d",
        severity=Severity.MEDIUM,
    )
    alvo = Target(asset_type=AssetType.URL, value=url.split("?")[0])
    async with session() as s:
        await registrar_ativos(s, scan_id, alvo, [f], scanners_ran=["zap"])
        await s.commit()
        ativo = await s.get(AssetRow, f.asset_id)
    assert ativo is not None
    assert "alvo@banco.com.br" not in ativo.value and "529.982.247-25" not in ativo.value


def test_cobertura_e_por_tipo_de_ativo() -> None:
    assert cobertura_do_tipo("port", ["nmap"], {}) is True
    # Nada pulado, mas ninguém que enxerga porta rodou: não é cobertura completa.
    assert cobertura_do_tipo("port", ["zap"], {}) is False
    # Um dos que enxergam URL foi pulado: parcial.
    assert cobertura_do_tipo("url", ["zap"], {"nuclei": "falhou"}) is False
    assert scanner_viu_o_tipo("host", ["nmap"]) and not scanner_viu_o_tipo("host", ["zap"])


async def test_busca_no_inventario_ignora_caixa_e_escapa_curinga(_data_dir) -> None:
    await init_db()
    marca = uuid.uuid4().hex[:6]
    async with session() as s:
        for valor in (f"http://Juice-{marca}:3000", f"http://outro{marca}x_y.test"):
            s.add(AssetRow(asset_key=uuid.uuid4().hex[:32], asset_type="url", value=valor))
        await s.commit()
    async with _cliente(Role.VIEWER) as c:
        achou = (await c.get("/inventory", params={"q": f"juice-{marca}"})).json()
        curinga = (await c.get("/inventory", params={"q": f"{marca}%"})).json()
        sublinhado = (await c.get("/inventory", params={"q": f"{marca}x_y"})).json()
    assert [a["value"] for a in achou["items"]] == [f"http://Juice-{marca}:3000"]
    assert curinga["items"] == [], "o % da busca virou curinga"
    assert len(sublinhado["items"]) == 1


# ============================================================ evidência no armazém


def test_proveniencia_e_hmac_e_some_sem_chave(_data_dir, monkeypatch) -> None:
    from cryptography.fernet import Fernet

    corpo = "cpf 529.982.247-25 do alvo"
    monkeypatch.setattr(settings, "SECRETS_KEY", "")
    assert store.put(corpo).original_sha256 == ""  # sem chave: nada quebrável
    monkeypatch.setattr(settings, "SECRETS_KEY", Fernet.generate_key().decode())
    prov = store.put(corpo).original_sha256
    assert prov.startswith("hmac-sha256:v1:")
    assert hashlib.sha256(corpo.encode()).hexdigest() not in prov


def test_corte_acontece_depois_do_scrubber(_data_dir) -> None:
    # O PAN atravessa o ponto de corte: cortar antes deixa os 8 primeiros dígitos (curtos
    # demais para a regex de PAN e sem Luhn) em claro no disco.
    texto = "x" * 16_375 + " 4111111111111111 fim"
    ref = store.put(texto, max_chars=16_384)
    gravado = store.get(ref.sha256).decode()
    assert "41111111" not in gravado
    assert "truncado em 16384" in gravado


def test_escritas_simultaneas_do_mesmo_blob_nao_corrompem(_data_dir) -> None:
    from concurrent.futures import ThreadPoolExecutor

    corpo = "mesmo corpo " * 50_000
    with ThreadPoolExecutor(max_workers=16) as pool:
        refs = list(pool.map(lambda _i: store.put(corpo), range(64)))
    assert len({r.sha256 for r in refs}) == 1
    assert store.get(refs[0].sha256)  # confere o hash: corpo íntegro
    sobras = [p.name for p in (_data_dir / "evidence").rglob("*.tmp")]
    assert sobras == []


def test_sha_invalido_nao_vira_caminho(_data_dir) -> None:
    with pytest.raises(store.EvidenceIntegrityError):
        store.get("../../etc/passwd")


# ================================================================== expurgo


async def _snapshot_de(texto: str, *, dias_atras: int) -> store.BlobRef:
    from datetime import UTC, datetime, timedelta

    ref = store.put(texto)
    async with session() as s:
        s.add(
            EvidenceSnapshotRow(
                sha256=ref.sha256,
                original_sha256=ref.original_sha256,
                created_at=datetime.now(UTC) - timedelta(days=dias_atras),
            )
        )
        await s.commit()
    return ref


async def test_expurgo_poupa_blob_tocado_ha_pouco(_data_dir) -> None:
    from orchestrator.evidence.service import expurgar_antigas

    await init_db()
    ref = await _snapshot_de(f"recém reaproveitado {uuid.uuid4()}", dias_atras=30)
    async with session() as s:
        apagados = await expurgar_antigas(s, 7, actor="adm@x")
    assert apagados == 0
    assert store.get(ref.sha256)  # uma captura em curso ainda vai apontar para ele


async def test_expurgo_que_falha_no_meio_ainda_audita(_data_dir, monkeypatch) -> None:
    from orchestrator.evidence.service import expurgar_antigas

    await init_db()
    velho = time.time() - 2 * 3600
    refs = [await _snapshot_de(f"velho {i} {uuid.uuid4()}", dias_atras=30) for i in range(2)]
    for r in refs:
        os.utime(store._path(r.sha256), (velho, velho))
    # O banco de teste é compartilhado: o expurgo também enxerga snapshots vencidos de
    # outros testes. A falha tem de cair no SEGUNDO hash deste teste, não na segunda
    # chamada qualquer (era o que deixava o teste intermitente).
    meus = sorted(r.sha256 for r in refs)
    original = store.purge

    def purge_que_falha(sha: str) -> bool:
        if sha == meus[1]:
            raise OSError("disco somente leitura")
        return original(sha)

    monkeypatch.setattr(store, "purge", purge_que_falha)
    async with session() as s:
        with pytest.raises(OSError):
            await expurgar_antigas(s, 7, actor="adm@x")
    async with session() as s:
        trilha = (
            await s.exec(
                select(AuditLogRow)
                .where(col(AuditLogRow.action) == "evidence.purge")
                .order_by(col(AuditLogRow.created_at).desc())
            )
        ).first()
    assert trilha is not None
    assert trilha.metadata_json.get("apagados") == 1
    assert "somente leitura" in str(trilha.metadata_json.get("erro"))


# ============================================================ rotas de evidência


async def test_bundle_nao_repete_blob_e_tem_teto(_data_dir, monkeypatch) -> None:
    import orchestrator.api.routers.evidence as rota

    await init_db()
    scan_id = uuid.uuid4()
    mesmo = store.put(f"mesmo corpo {uuid.uuid4()}")
    outro = store.put(f"outro corpo {uuid.uuid4()}")
    async with session() as s:
        for ref in (mesmo, mesmo, outro):
            s.add(EvidenceSnapshotRow(sha256=ref.sha256, original_sha256="", scan_id=scan_id))
        await s.commit()
    async with _cliente(Role.VIEWER) as c:
        resp = await c.get(f"/evidence/bundle/{scan_id}")
        assert resp.status_code == 200
        nomes = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
        assert sorted(n for n in nomes if n.startswith("blobs/")) == sorted(
            {f"blobs/{mesmo.sha256}", f"blobs/{outro.sha256}"}
        )
        monkeypatch.setattr(rota, "_BUNDLE_MAX_BLOBS", 1)
        assert (await c.get(f"/evidence/bundle/{scan_id}")).status_code == 413


async def test_blob_rejeita_sha_mal_formado() -> None:
    async with _cliente(Role.VIEWER) as c:
        assert (await c.get("/evidence/blob/..%2F..%2Fetc%2Fpasswd")).status_code in (404, 422)
        assert (await c.get("/evidence/blob/ZZZ")).status_code == 422


async def test_original_cifrado_exige_config_manage_e_fica_na_trilha(
    _data_dir, monkeypatch
) -> None:
    from cryptography.fernet import Fernet

    await init_db()
    monkeypatch.setattr(settings, "SECRETS_KEY", Fernet.generate_key().decode())
    ref = store.put("cpf 529.982.247-25 em claro", encrypt=True)
    async with session() as s:
        s.add(EvidenceSnapshotRow(sha256=ref.sha256, original_sha256="", encrypted=True))
        await s.commit()
    async with _cliente(Role.VIEWER) as c:
        assert (await c.get(f"/evidence/blob/{ref.sha256}")).status_code == 403
    async with _cliente(Role.ADMIN, email="dpo@x") as c:
        resp = await c.get(f"/evidence/blob/{ref.sha256}")
    assert resp.status_code == 200 and "529.982.247-25" in resp.text
    async with session() as s:
        lida = (
            await s.exec(
                select(AuditLogRow)
                .where(col(AuditLogRow.action) == "evidence.read_original")
                .where(col(AuditLogRow.actor) == "dpo@x")
            )
        ).first()
    assert lida is not None


# ===================================================== scan em andamento, aprovações


async def test_scan_em_andamento_nao_pode_ser_apagado() -> None:
    await init_db()
    scan_id = uuid.uuid4()
    async with session() as s:
        alvo = TargetRow(asset_type="host", value=f"rodando-{scan_id}.test")
        s.add(alvo)
        await s.flush()
        s.add(ScanRow(id=scan_id, target_id=alvo.id, state=ScanState.RUNNING.value))
        await s.commit()
    async with _cliente(Role.ADMIN) as c:
        resp = await c.delete(f"/scans/{scan_id}")
    assert resp.status_code == 409
    async with session() as s:
        assert await s.get(ScanRow, scan_id) is not None


async def test_reason_da_aprovacao_tem_limite_e_e_redigido() -> None:
    from orchestrator.approvals import service

    await init_db()
    async with session() as s:
        aid = (await service.criar_pendencia(s, command="nmap x", proposed_by="op@x")).id
    async with _cliente(Role.ADMIN, email="adm@x") as c:
        longo = await c.post(f"/approvals/{aid}/deny", json={"reason": "x" * 2001})
        assert longo.status_code == 422
        ok = await c.post(
            f"/approvals/{aid}/deny", json={"reason": "negado: senha=hunter2 no argv"}
        )
    assert ok.status_code == 200
    async with session() as s:
        row = await s.get(CommandApprovalRow, aid)
    assert row is not None and row.reason is not None and "hunter2" not in row.reason


async def test_listagem_de_aprovacoes_pagina() -> None:
    from orchestrator.approvals import service

    await init_db()
    async with session() as s:
        for _ in range(3):
            await service.criar_pendencia(s, command="nmap x", proposed_by="op@x")
    async with _cliente(Role.ADMIN, email="adm@x") as c:
        assert len((await c.get("/approvals", params={"limit": 2})).json()) == 2


# ============================================================== boot


def test_boot_recusa_modo_cifrado_sem_chave() -> None:
    erros = insecure_boot_errors(
        Settings(APP_TOKEN="x" * 40, EVIDENCE_ENCRYPT_ORIGINAL=True, SECRETS_KEY="")
    )
    assert any("EVIDENCE_ENCRYPT_ORIGINAL" in e for e in erros)


def test_escape_do_token_nao_desliga_as_outras_checagens() -> None:
    erros = insecure_boot_errors(
        Settings(
            ALLOW_INSECURE_APP_TOKEN=True,
            REQUIRE_IMMUTABLE_AUDIT=True,
            DATABASE_URL="sqlite+aiosqlite:///x.db",
        )
    )
    assert any("REQUIRE_IMMUTABLE_AUDIT" in e for e in erros)
