"""Inventário de ativos entre scans (Frente A).

Um ativo (host, porta, URL, imagem, repo, domínio, recurso k8s) persiste ENTRE scans.
A identidade é a `asset_key` — determinística, no molde da `Finding.deduped_key`: o mesmo
alvo em dois scans produz a MESMA chave, então a linha de `AssetRow` é reusada (upsert) e
o `id` UUID permanece estável. O finding aponta para esse `id`.

A matéria-prima do inventário já existe: cada `Finding` carrega no próprio `.target` o ativo
exato que o scanner viu (o nmap emite `Target(asset_type=PORT, value="host:porta/proto")`,
o ZAP emite `AssetType.URL`, etc.). O agregador lê essa identidade estruturada — não parseia
título.

O contrato do silêncio vale aqui: um ativo que não reapareceu num scan só é "sumiu" se o
scanner que o enxerga RODOU com cobertura; senão é "não verificado" (ver
`classificar_presenca`). Zero observações de um ativo com o nmap derrubado não é "a porta
fechou", é "ninguém olhou".
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from orchestrator.domain.scrubber import scrub

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from orchestrator.domain.schemas import Finding, Target


# Qual(is) scanner(es) enxerga(m) cada tipo de ativo. É o eixo de "sumiu" vs "não
# verificado": se nenhum scanner que vê o tipo rodou, a ausência não é informação.
_VE_O_TIPO: dict[str, frozenset[str]] = {
    "host": frozenset({"nmap"}),
    "port": frozenset({"nmap"}),
    "url": frozenset({"zap", "nuclei"}),
    "domain": frozenset({"dnstwist", "subdomain_takeover"}),
    "image": frozenset({"trivy"}),
    "repo": frozenset({"semgrep", "gitleaks", "trufflehog", "checkov"}),
    "k8s_resource": frozenset({"kube_bench"}),
}


def _normalizar(asset_type: str, value: str) -> str:
    """Forma canônica do valor para a chave — some variação trivial (barra final, caixa
    do host), sem mexer no que é sensível a caixa (o path de uma URL)."""
    v = value.strip()
    if asset_type in ("host", "domain"):
        return v.lower().rstrip(".")
    if asset_type == "port":
        # "host:porta/proto" — só o host é case-insensitive.
        return v.lower()
    if asset_type == "url":
        # Caixa do esquema e do host não distingue ativo (DNS é case-insensitive); o
        # path, sim. Dobra netloc/scheme, preserva o resto. `https://A.test/x` e
        # `https://a.test/x` viram a mesma chave, mas `/X` e `/x` seguem distintos.
        partes = urlsplit(v.rstrip("/"))
        if partes.netloc:
            return urlunsplit(
                (partes.scheme.lower(), partes.netloc.lower(), partes.path, partes.query, "")
            )
        return v.rstrip("/")
    return v


def asset_key(asset_type: str, value: str) -> str:
    """Identidade determinística do ativo: sha256(tipo::valor_normalizado)[:32].

    Estável entre scans para o mesmo alvo — é o que faz o inventário reconhecer o
    ativo de ontem no scan de hoje em vez de criar um duplicado.
    """
    material = f"{asset_type}::{_normalizar(asset_type, value)}".encode()
    return hashlib.sha256(material).hexdigest()[:32]


def classificar_presenca(
    asset_type: str,
    *,
    observado_no_scan: bool,
    scanners_ran: list[str],
) -> str:
    """ "present" | "disappeared" | "not_verified" de um ativo num scan.

    - observado: o scan viu o ativo → "present".
    - não observado, mas um scanner que enxerga o tipo rodou → "disappeared" (sumiu de verdade).
    - não observado e ninguém que enxerga o tipo rodou → "not_verified" (ninguém olhou).

    `scanners_ran` já exclui os pulados (o pipeline só adiciona em caso de sucesso),
    então rodar == ter cobertura daquele vetor.
    """
    if observado_no_scan:
        return "present"
    veem = _VE_O_TIPO.get(asset_type, frozenset())
    if veem & set(scanners_ran):
        return "disappeared"
    return "not_verified"


def _coletar_observacoes(
    target: Target,
    findings: list[Finding],
) -> dict[str, tuple[str, str, str | None, str | None]]:
    """Dedup das observações do scan: asset_key -> (asset_type, value, label, source_tool).

    O alvo do scan entra sempre (visto, mesmo sem achado); cada finding contribui com o
    ativo do seu próprio `.target`. O primeiro a registrar a chave define o source_tool
    (o alvo do scan, sem tool, não sobrescreve um tool real que venha depois)."""
    obs: dict[str, tuple[str, str, str | None, str | None]] = {}
    k = asset_key(target.asset_type.value, target.value)
    obs[k] = (target.asset_type.value, target.value, target.label, None)
    for f in findings:
        t = f.target
        kk = asset_key(t.asset_type.value, t.value)
        if kk not in obs or obs[kk][3] is None:
            label = scrub(t.label) if t.label else None
            obs[kk] = (t.asset_type.value, t.value, label, f.source_tool)
    return obs


async def registrar_ativos(
    session: AsyncSession,
    scan_id: UUID,
    target: Target,
    findings: list[Finding],
) -> dict[str, UUID]:
    """Faz upsert dos ativos vistos no scan e preenche `Finding.asset_id`.

    Dentro da MESMA sessão/transação do `_persist_findings` (o caller comita). Devolve o
    mapa asset_key -> asset_id para quem quiser. Cada finding sai com `asset_id` setado a
    partir do ativo do seu `.target`.
    """
    from orchestrator.persistence.models import AssetObservationRow, AssetRow

    obs = _coletar_observacoes(target, findings)
    key_to_id: dict[str, UUID] = {}

    def _reaparecer(row: AssetRow) -> AssetRow:
        # Reaparecimento: só move last_seen/last_scan; first_seen nunca é reescrito.
        row.last_seen = datetime.now(UTC)
        row.last_scan_id = scan_id
        if label and not row.label:
            row.label = label
        session.add(row)
        return row

    for chave, (atype, value, label, tool) in obs.items():
        row = (await session.exec(select(AssetRow).where(AssetRow.asset_key == chave))).first()
        if row is None:
            novo = AssetRow(
                asset_key=chave,
                asset_type=atype,
                value=value,
                label=label,
                last_scan_id=scan_id,
            )
            session.add(novo)
            try:
                # Savepoint: se dois workers escaneiam o mesmo host novo, o segundo bate
                # na unique de asset_key. Sem isto o IntegrityError no flush derrubaria o
                # persist inteiro e os findings do scan se perderiam. O savepoint isola a
                # falha; recarrego a linha que o outro worker gravou e sigo.
                async with session.begin_nested():
                    await session.flush()
                row = novo
            except IntegrityError:
                existente = (
                    await session.exec(select(AssetRow).where(AssetRow.asset_key == chave))
                ).first()
                if existente is None:
                    raise
                row = _reaparecer(existente)
        else:
            row = _reaparecer(row)
        key_to_id[chave] = row.id

        # Observação idempotente: uma por (ativo, scan).
        ja = (
            await session.exec(
                select(AssetObservationRow)
                .where(AssetObservationRow.asset_id == row.id)
                .where(AssetObservationRow.scan_id == scan_id)
            )
        ).first()
        if ja is None:
            session.add(AssetObservationRow(asset_id=row.id, scan_id=scan_id, source_tool=tool))

    for f in findings:
        f.asset_id = key_to_id.get(asset_key(f.target.asset_type.value, f.target.value))

    return key_to_id
