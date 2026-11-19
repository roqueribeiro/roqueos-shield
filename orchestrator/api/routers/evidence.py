"""Evidence router: evidência que se sustenta (Frente C).

`GET /evidence/finding/{deduped_key}` lista as evidências de um problema; `GET
/evidence/blob/{sha256}` devolve o corpo com o hash CONFERIDO (corpo ausente → 410,
corrompido → 422); `GET /evidence/bundle/{scan_id}` empacota tudo num zip com manifesto e
hashes — um arquivo ausente ou corrompido derruba o download inteiro, de propósito.
`POST /evidence/purge` roda a retenção (apaga corpo, mantém hash e registro, audita).
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Response
from pydantic import BaseModel
from sqlmodel import col, select

from orchestrator.api.deps import Principal, RequireConfigManage, RequireScansRead, SessionDep
from orchestrator.audit.logger import log_audit_event
from orchestrator.config import settings
from orchestrator.domain.roles import Permission, has_permission
from orchestrator.evidence import store
from orchestrator.evidence.service import expurgar_antigas
from orchestrator.persistence.models import EvidenceLinkRow, EvidenceSnapshotRow

router = APIRouter(prefix="/evidence", tags=["evidence"])

# Teto do bundle: o zip é montado em memória. Acima disto a rota recusa com 413 em vez de
# segurar centenas de MB por pedido; recusar é visível, cortar em silêncio não seria.
_BUNDLE_MAX_BLOBS = 5_000
_BUNDLE_MAX_BYTES = 256 * 1024 * 1024
_SHA256_DA_URL = Path(pattern=r"^[0-9a-f]{64}$", description="sha256 do corpo gravado")


class EvidenceItemOut(BaseModel):
    snapshot_id: UUID
    sha256: str
    original_sha256: str
    papel: str
    ordem: int
    evidence_version: int
    content_type: str
    size_bytes: int
    encrypted: bool
    nota: str | None
    created_at: datetime


class PurgeOut(BaseModel):
    purged: int
    retention_days: int


async def _itens_do_problema(session: SessionDep, deduped_key: str) -> list[EvidenceItemOut]:
    links = (
        await session.exec(
            select(EvidenceLinkRow)
            .where(EvidenceLinkRow.deduped_key == deduped_key)
            .order_by(col(EvidenceLinkRow.evidence_version), col(EvidenceLinkRow.ordem))
        )
    ).all()
    itens: list[EvidenceItemOut] = []
    for link in links:
        snap = await session.get(EvidenceSnapshotRow, link.snapshot_id)
        if snap is None:
            continue
        itens.append(
            EvidenceItemOut(
                snapshot_id=snap.id,
                sha256=snap.sha256,
                original_sha256=snap.original_sha256,
                papel=link.papel,
                ordem=link.ordem,
                evidence_version=link.evidence_version,
                content_type=snap.content_type,
                size_bytes=snap.size_bytes,
                encrypted=snap.encrypted,
                nota=link.nota,
                created_at=snap.created_at,
            )
        )
    return itens


@router.get("/finding/{deduped_key}", response_model=list[EvidenceItemOut])
async def list_evidence(
    deduped_key: str,
    session: SessionDep,
    _principal: Principal = RequireScansRead,
) -> list[EvidenceItemOut]:
    """Evidências de um problema (pela `deduped_key`), por versão e ordem. `scans:read`."""
    return await _itens_do_problema(session, deduped_key)


@router.get("/blob/{sha256}")
async def get_blob(
    session: SessionDep,
    sha256: str = _SHA256_DA_URL,
    principal: Principal = RequireScansRead,
) -> Response:
    """O corpo da evidência, com o hash conferido. `scans:read`.

    410 se o corpo foi expurgado (o registro fica, o corpo não); 422 se o que está em
    disco não bate com o hash (corrompido/adulterado); 404 se não há snapshot com esse sha.

    Blob cifrado é o ORIGINAL, com o PII que o modo redigido apaga: decifrar exige
    `config:manage` e fica na trilha (`evidence.read_original`), com o ator. Antes,
    qualquer `scans:read` recebia o original em claro sem deixar registro.
    """
    snap = (
        await session.exec(select(EvidenceSnapshotRow).where(EvidenceSnapshotRow.sha256 == sha256))
    ).first()
    if snap is None:
        raise HTTPException(status_code=404, detail="evidência não encontrada")
    if snap.encrypted and not has_permission(principal.role, Permission.CONFIG_MANAGE):
        raise HTTPException(
            status_code=403,
            detail="evidência cifrada é o original com dado pessoal: exige config:manage",
        )
    try:
        # ler_claro confere o hash e, se o blob for o original cifrado, decifra.
        data = store.ler_claro(sha256, encrypted=snap.encrypted)
    except store.EvidenceExpurgada as e:
        raise HTTPException(status_code=410, detail=f"corpo expurgado pela retenção: {e}") from e
    except store.EvidenceIntegrityError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if snap.encrypted:
        await log_audit_event(
            session,
            action="evidence.read_original",
            actor=principal.email,
            resource_type="evidence",
            resource_id=snap.id,
            metadata={"sha256": sha256},
        )
        await session.commit()
    return Response(content=data, media_type=snap.content_type)


@router.get("/bundle/{scan_id}")
async def get_bundle(
    scan_id: UUID,
    session: SessionDep,
    _principal: Principal = RequireScansRead,
) -> Response:
    """Zip com todas as evidências de um scan: `manifest.json` (com os hashes) e os corpos.

    Um corpo ausente ou corrompido derruba o download inteiro (422/410): um pacote de
    prova pela metade é pior que nenhum. `scans:read`.
    """
    snaps = (
        await session.exec(
            select(EvidenceSnapshotRow)
            .where(EvidenceSnapshotRow.scan_id == scan_id)
            .order_by(col(EvidenceSnapshotRow.created_at))
        )
    ).all()
    if not snaps:
        raise HTTPException(status_code=404, detail="scan sem evidência")

    # Dois achados com o mesmo corpo geram dois snapshots com o mesmo sha: um blob só no
    # zip (entrada duplicada no zip é ambígua), e o teto vale para o que de fato entra.
    unicos = list({snap.sha256: snap for snap in snaps}.values())
    total = sum(snap.size_bytes for snap in unicos)
    if len(unicos) > _BUNDLE_MAX_BLOBS or total > _BUNDLE_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"bundle grande demais: {len(unicos)} corpos, {total} bytes "
                f"(teto {_BUNDLE_MAX_BLOBS} corpos, {_BUNDLE_MAX_BYTES} bytes)"
            ),
        )

    buffer = io.BytesIO()
    manifesto: list[dict[str, object]] = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for snap in unicos:
            try:
                # O bundle é verificável por hash: empacota os BYTES ARMAZENADOS (store.get
                # confere o sha256), para o arquivo bater com o `sha256` do manifesto. Não
                # decifra aqui — o manifesto carrega `encrypted` e `original_sha256`, e o
                # destinatário com a SECRETS_KEY decifra offline. (A rota /blob decifra para
                # ver ao vivo; o bundle, não, senão o hash do arquivo divergiria do manifesto.)
                data = store.get(snap.sha256)
            except store.EvidenceExpurgada as e:
                raise HTTPException(
                    status_code=410, detail=f"corpo {snap.sha256} expurgado: {e}"
                ) from e
            except store.EvidenceIntegrityError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            nome = f"blobs/{snap.sha256}"
            zf.writestr(nome, data)
            manifesto.append(
                {
                    "sha256": snap.sha256,
                    "original_sha256": snap.original_sha256,
                    "content_type": snap.content_type,
                    "size_bytes": snap.size_bytes,
                    "encrypted": snap.encrypted,
                    "path": nome,
                }
            )
        zf.writestr(
            "manifest.json",
            json.dumps({"scan_id": str(scan_id), "blobs": manifesto}, ensure_ascii=False, indent=2),
        )
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="evidence-{scan_id}.zip"'},
    )


@router.post("/purge", response_model=PurgeOut)
async def purge_evidence(
    session: SessionDep,
    principal: Principal = RequireConfigManage,
) -> PurgeOut:
    """Roda a retenção (`EVIDENCE_RETENTION_DAYS`): apaga o corpo dos snapshots vencidos,
    mantém hash e registro, audita `evidence.purge`. `config:manage`."""
    dias = settings.EVIDENCE_RETENTION_DAYS
    apagados = await expurgar_antigas(session, dias, actor=principal.email)
    return PurgeOut(purged=apagados, retention_days=dias)
