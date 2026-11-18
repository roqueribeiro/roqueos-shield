"""Inventário de ativos — persistência entre scans (Frente A).

Prova o que a função pura não prova: que o ativo do scan de ontem é RECONHECIDO no scan
de hoje (mesma `asset_key`, mesma linha reusada, `first_seen` intacto) e que o finding
sai ligado ao ativo. Afirma sobre o dado PERSISTIDO, como manda a regra de cobertura.
"""

from __future__ import annotations

import uuid

from sqlmodel import col, select

from orchestrator.domain.assets import asset_key, registrar_ativos
from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Evidence,
    Finding,
    Severity,
    Target,
)
from orchestrator.persistence.db import init_db, session
from orchestrator.persistence.models import AssetObservationRow, AssetRow


def _finding_porta(scan_id: uuid.UUID, host: str = "10.0.0.1", porta: int = 80) -> Finding:
    return Finding(
        scan_id=scan_id,
        target=Target(asset_type=AssetType.PORT, value=f"{host}:{porta}/tcp", label="http"),
        source_tool="nmap",
        source_rule_id=f"port-{porta}-tcp",
        title=f"Open port {porta}/tcp",
        description="aberta",
        severity=Severity.INFO,
        confidence=Confidence.CERTAIN,
        evidence=[Evidence(description="banner", snippet="nginx")],
    )


async def test_inventario_liga_finding_ao_ativo_e_cria_host_e_porta() -> None:
    await init_db()
    alvo = Target(asset_type=AssetType.HOST, value="10.0.0.1")
    scan1 = uuid.uuid4()
    f1 = _finding_porta(scan1)

    async with session() as s:
        await registrar_ativos(s, scan1, alvo, [f1], scanners_ran=["nmap"])
        await s.commit()

    # O finding sai com asset_id setado (o ativo do seu próprio target: a porta).
    assert f1.asset_id is not None

    async with session() as s:
        chaves = {a.asset_key for a in (await s.exec(select(AssetRow))).all()}
    # Host (alvo do scan) e porta (target do finding) viram ativos.
    assert asset_key("host", "10.0.0.1") in chaves
    assert asset_key("port", "10.0.0.1:80/tcp") in chaves


async def test_asset_key_estavel_entre_dois_scans_do_mesmo_alvo() -> None:
    await init_db()
    alvo = Target(asset_type=AssetType.HOST, value="10.0.0.2")
    chave_porta = asset_key("port", "10.0.0.2:22/tcp")

    # Scan 1
    scan1 = uuid.uuid4()
    async with session() as s:
        await registrar_ativos(
            s,
            scan1,
            alvo,
            [_finding_porta(scan1, host="10.0.0.2", porta=22)],
            scanners_ran=["nmap"],
        )
        await s.commit()
    async with session() as s:
        ativo1 = (await s.exec(select(AssetRow).where(AssetRow.asset_key == chave_porta))).one()
        id1, first_seen1 = ativo1.id, ativo1.first_seen

    # Scan 2, mesmo alvo e mesma porta
    scan2 = uuid.uuid4()
    async with session() as s:
        await registrar_ativos(
            s,
            scan2,
            alvo,
            [_finding_porta(scan2, host="10.0.0.2", porta=22)],
            scanners_ran=["nmap"],
        )
        await s.commit()

    async with session() as s:
        # A linha é a MESMA (reuso por asset_key), não um duplicado.
        linhas = (await s.exec(select(AssetRow).where(AssetRow.asset_key == chave_porta))).all()
        assert len(linhas) == 1
        ativo2 = linhas[0]
        assert ativo2.id == id1  # id estável entre scans
        assert ativo2.first_seen == first_seen1  # first_seen nunca reescrito
        assert ativo2.last_scan_id == scan2  # last_scan avança

        # Uma observação por scan: o ativo foi visto nos dois.
        obs = (
            await s.exec(
                select(AssetObservationRow)
                .where(AssetObservationRow.asset_id == id1)
                .order_by(col(AssetObservationRow.observed_at))
            )
        ).all()
        assert {o.scan_id for o in obs} == {scan1, scan2}
