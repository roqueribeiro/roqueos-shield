"""Código enviado para scan: `POST /code/{projeto}/uploads` recebe um `.tar.gz`.

Para o agente ou o CI que precisa avaliar código que não está num git alcançável pelo
worker (árvore ainda não commitada, repo privado). O corpo é o tarball cru
(`Content-Type: application/gzip`), não multipart: o proxy do RoqueOS repassa corpo
binário sem reescrever, e não há dependência nova.

O fluxo é em dois passos, de propósito:

1. `POST /code/{projeto}/uploads` grava o tarball, confere que ele é extraível sem
   escapar da raiz (`domain/codigo.py`), cria o alvo `code://<projeto>` se faltar e
   devolve `upload_id` + `target_id`;
2. `POST /scans` com `target_id` e `code_upload_id` passa pelos mesmos portões de todo
   scan (`authorization_ref` quando `REQUIRE_AUTH_REF`, trilha de auditoria, rate limit).

Assim o envio não é um atalho para fora dos gates: ele só entrega o código.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import select

from orchestrator import codigo_enviado
from orchestrator.api.deps import Principal, SessionDep, require_permission
from orchestrator.api.ratelimit import rate_limit
from orchestrator.audit import log_audit_event
from orchestrator.config import settings
from orchestrator.domain.codigo import CodigoRecusado, alvo_do_projeto, inspecionar
from orchestrator.domain.roles import Permission
from orchestrator.domain.schemas import AssetType
from orchestrator.persistence.models import TargetRow

router = APIRouter(prefix="/code", tags=["code"])

_RUN = Depends(require_permission(Permission.SCANS_RUN))
_TIPOS = {"application/gzip", "application/x-gzip", "application/octet-stream"}


class CodeUploadOut(BaseModel):
    upload_id: UUID
    target_id: UUID
    target_value: str
    sha256: str
    bytes_comprimidos: int
    arquivos: int
    bytes_descomprimidos: int
    expira_em: datetime


@router.post(
    "/{projeto}/uploads",
    response_model=CodeUploadOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("code"))],
)
async def upload_code(
    projeto: str,
    request: Request,
    session: SessionDep,
    principal: Principal = _RUN,
) -> CodeUploadOut:
    """Recebe a árvore de código como `.tar.gz` e prepara o alvo `code://<projeto>`."""
    try:
        alvo = alvo_do_projeto(projeto)
    except CodigoRecusado as e:
        raise HTTPException(422, str(e)) from e
    tipo = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if tipo not in _TIPOS:
        raise HTTPException(415, "envie o .tar.gz cru com Content-Type: application/gzip")

    teto = settings.CODE_UPLOAD_MAX_MB * 1024 * 1024
    upload_id = uuid4()
    destino = codigo_enviado.tarball(upload_id)
    parcial = destino.with_name(destino.name + ".parcial")
    h = hashlib.sha256()
    recebido = 0
    try:
        with parcial.open("wb") as fh:
            async for pedaco in request.stream():
                recebido += len(pedaco)
                if recebido > teto:
                    raise HTTPException(
                        413, f"o envio passa de {settings.CODE_UPLOAD_MAX_MB} MB comprimido"
                    )
                h.update(pedaco)
                fh.write(pedaco)
        if recebido == 0:
            raise HTTPException(422, "corpo vazio: envie o .tar.gz da árvore")
        try:
            inv = inspecionar(
                parcial,
                max_arquivos=settings.CODE_UPLOAD_MAX_FILES,
                max_bytes=settings.CODE_UPLOAD_MAX_EXTRACTED_MB * 1024 * 1024,
            )
        except CodigoRecusado as e:
            raise HTTPException(422, f"envio recusado: {e}") from e
        os.replace(parcial, destino)
    finally:
        parcial.unlink(missing_ok=True)

    alvo_row = (
        await session.exec(
            select(TargetRow).where(
                TargetRow.value == alvo, TargetRow.asset_type == AssetType.REPO.value
            )
        )
    ).first()
    if alvo_row is None:
        alvo_row = TargetRow(asset_type=AssetType.REPO.value, value=alvo, label=projeto)
        session.add(alvo_row)
        await session.flush()

    envio = codigo_enviado.Envio(
        upload_id=str(upload_id),
        projeto=alvo.removeprefix("code://"),
        sha256=h.hexdigest(),
        bytes_comprimidos=recebido,
        arquivos=inv.arquivos,
        bytes_descomprimidos=inv.bytes_descomprimidos,
        criado_em=datetime.now(UTC).isoformat(),
        actor=principal.email,
    )
    try:
        codigo_enviado.gravar_meta(envio)
        await log_audit_event(
            session,
            action="code.upload",
            actor=principal.email,
            resource_type="target",
            resource_id=alvo_row.id,
            metadata={
                "upload_id": envio.upload_id,
                "target_value": alvo,
                "sha256": envio.sha256,
                "bytes": recebido,
                "arquivos": inv.arquivos,
            },
        )
        await session.commit()
    except Exception:
        # Sem trilha não há envio: o código não pode ficar no disco sem registro.
        codigo_enviado.apagar(upload_id)
        raise

    return CodeUploadOut(
        upload_id=upload_id,
        target_id=alvo_row.id,
        target_value=alvo,
        sha256=envio.sha256,
        bytes_comprimidos=recebido,
        arquivos=inv.arquivos,
        bytes_descomprimidos=inv.bytes_descomprimidos,
        expira_em=envio.expira_em,
    )
