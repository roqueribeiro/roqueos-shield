"""Captura e retenção de evidência (Frente C).

Liga o armazém (`store.py`) às tabelas: ao persistir um achado, cada `Evidence` vira um
snapshot redigido + um vínculo (`proof`) pelo `deduped_key` do problema. A retenção apaga
o corpo dos snapshots vencidos e deixa hash e registro, com um evento `evidence.purge` na
trilha de auditoria.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlmodel import col, func, select

from orchestrator.evidence import store
from orchestrator.persistence.models import EvidenceLinkRow, EvidenceSnapshotRow

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from orchestrator.domain.schemas import Finding

# Corpo de evidência é recorte, não dump: um request/response gigante vira ruído no
# relatório e peso no armazém. O corte acontece no armazém, DEPOIS do scrubber.
_MAX_CHARS = 16_384
# Blob gravado ou reaproveitado há menos que isto não é expurgado: uma captura em curso
# reaproveita o blob de mesmo conteúdo antes de comitar o snapshot, e o expurgo (que só
# enxerga linhas comitadas) apagaria o corpo de uma prova que acabou de nascer.
_JANELA_DE_CAPTURA_S = 3600


def _corpo_da_evidencia(ev: object) -> str | None:
    """Junta os campos de texto de um `Evidence` num corpo rotulado, ou None se vazio."""
    partes: list[str] = []
    for campo in ("description", "request", "response", "payload", "snippet"):
        valor = getattr(ev, campo, None)
        if valor:
            partes.append(f"[{campo}]\n{valor}")
    if not partes:
        return None
    return "\n\n".join(partes)


async def _proxima_versao(session: AsyncSession, deduped_key: str) -> int:
    atual = (
        await session.exec(
            select(func.max(EvidenceLinkRow.evidence_version)).where(
                EvidenceLinkRow.deduped_key == deduped_key
            )
        )
    ).one()
    return int(atual or 0) + 1


async def capturar_evidencias(session: AsyncSession, scan_id: UUID, finding: Finding) -> int:
    """Guarda as evidências de um achado como snapshots redigidos + vínculos `proof`.

    Dentro da sessão do `_persist_findings` (o caller comita). Devolve quantos snapshots
    gravou. O corpo é redigido pelo armazém ANTES de ir para disco.
    """
    if not finding.evidence:
        return 0
    versao = await _proxima_versao(session, finding.deduped_key)
    gravados = 0
    for ordem, ev in enumerate(finding.evidence):
        corpo = _corpo_da_evidencia(ev)
        if corpo is None:
            continue
        ref = store.put(corpo, content_type="text/plain", max_chars=_MAX_CHARS)
        snap = EvidenceSnapshotRow(
            sha256=ref.sha256,
            original_sha256=ref.original_sha256,
            content_type=ref.content_type,
            size_bytes=ref.size_bytes,
            encrypted=ref.encrypted,
            scan_id=scan_id,
        )
        session.add(snap)
        await session.flush()  # materializa o id do snapshot para o vínculo
        session.add(
            EvidenceLinkRow(
                deduped_key=finding.deduped_key,
                snapshot_id=snap.id,
                papel="proof",
                ordem=ordem,
                evidence_version=versao,
            )
        )
        gravados += 1
    return gravados


async def expurgar_antigas(session: AsyncSession, dias: int, *, actor: str | None = None) -> int:
    """Apaga o CORPO dos snapshots mais velhos que `dias` (0 = nunca expurga). Mantém hash
    e registro; audita `evidence.purge`. Devolve quantos corpos foram apagados."""
    if dias <= 0:
        return 0
    from orchestrator.audit.logger import log_audit_event

    limite = datetime.now(UTC) - timedelta(days=dias)
    # O blob é endereçado por conteúdo e COMPARTILHADO: dois snapshots com o mesmo corpo
    # apontam para o mesmo arquivo. Apagar pelo snapshot velho destruía a prova de um
    # snapshot novo, ainda dentro da retenção, com o mesmo sha256. Só sai o hash que
    # nenhum snapshot dentro da retenção usa.
    vencidos = set(
        (
            await session.exec(
                select(EvidenceSnapshotRow.sha256).where(
                    col(EvidenceSnapshotRow.created_at) < limite
                )
            )
        ).all()
    )
    vivos = set(
        (
            await session.exec(
                select(EvidenceSnapshotRow.sha256).where(
                    col(EvidenceSnapshotRow.created_at) >= limite
                )
            )
        ).all()
    )
    preservados = vencidos & vivos
    apagados = 0
    em_uso = 0
    erro: str | None = None
    try:
        for sha in sorted(vencidos - vivos):
            if store.tocado_ha_menos_de(sha, _JANELA_DE_CAPTURA_S):
                em_uso += 1  # reaproveitado há pouco por uma captura que ainda não comitou
                continue
            # Confere de novo, colado ao unlink: um snapshot em retenção pode ter
            # aparecido desde a leitura de `vivos`.
            ainda_vivo = (
                await session.exec(
                    select(EvidenceSnapshotRow.id)
                    .where(col(EvidenceSnapshotRow.sha256) == sha)
                    .where(col(EvidenceSnapshotRow.created_at) >= limite)
                    .limit(1)
                )
            ).first()
            if ainda_vivo is not None:
                preservados.add(sha)
                continue
            if store.purge(sha):
                apagados += 1
    except OSError as e:
        erro = str(e)
        raise
    finally:
        # Audita SEMPRE que algo saiu do disco ou foi poupado, inclusive se o expurgo
        # falhou no meio: corpo apagado sem registro na trilha é exatamente o que um
        # auditor não pode encontrar.
        if apagados or preservados or em_uso or erro:
            metadata: dict[str, object] = {
                "dias": dias,
                "apagados": apagados,
                "preservados_por_referencia": len(preservados),
                "poupados_em_uso": em_uso,
            }
            if erro:
                metadata["erro"] = erro
            await log_audit_event(
                session,
                action="evidence.purge",
                actor=actor,
                resource_type="evidence",
                metadata=metadata,
            )
            await session.commit()
    return apagados
