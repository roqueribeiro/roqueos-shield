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


def _identidade(asset_type: str, value: str) -> tuple[str, str]:
    """(valor gravado, asset_key) de um ativo.

    O valor passa pelo scrubber ANTES de virar chave e de ir para o banco. Uma URL com
    `?cpf=...` ou `?access_token=...` chegava ao inventário em claro, aparecia em
    `GET /inventory` para qualquer `scans:read`, era pesquisável por `q=` e sobrevivia ao
    delete do scan (o ativo persiste de propósito). De quebra, variações só no valor
    sensível colapsam no mesmo ativo em vez de inflar o inventário."""
    limpo = scrub(value)
    return limpo, asset_key(asset_type, limpo)


def scanner_viu_o_tipo(asset_type: str, scanners_ran: list[str]) -> bool:
    """Algum scanner que enxerga este tipo de ativo rodou neste scan?"""
    return bool(_VE_O_TIPO.get(asset_type, frozenset()) & set(scanners_ran))


def cobertura_do_tipo(
    asset_type: str, scanners_ran: list[str], scanners_skipped: list[str] | dict[str, str]
) -> bool:
    """Cobertura completa PARA ESTE TIPO de ativo: rodou quem o enxerga e nenhum dos que o
    enxergam foi pulado. "O scan não pulou nada" não basta: um scan sem scanner aplicável
    ao tipo também não pula nada, e não viu coisa alguma."""
    veem = _VE_O_TIPO.get(asset_type, frozenset())
    return bool(veem & set(scanners_ran)) and not (veem & set(scanners_skipped))


def _coletar_observacoes(
    target: Target,
    findings: list[Finding],
    scanners_ran: list[str],
) -> dict[str, tuple[str, str, str | None, str | None]]:
    """Dedup das observações do scan: asset_key -> (asset_type, value, label, source_tool).

    Cada finding contribui com o ativo do seu próprio `.target` (o achado prova que alguém
    olhou). O alvo do scan só entra se um scanner que enxerga o tipo dele RODOU: com o
    nmap pulado e o scan `failed`, gravar "o host foi visto agora" seria o contrato do
    silêncio ao contrário, presença afirmada por quem não olhou. O primeiro a registrar a
    chave define o source_tool (o alvo, sem tool, não sobrescreve um tool real)."""
    obs: dict[str, tuple[str, str, str | None, str | None]] = {}
    if scanner_viu_o_tipo(target.asset_type.value, scanners_ran):
        valor, k = _identidade(target.asset_type.value, target.value)
        label = scrub(target.label) if target.label else None
        obs[k] = (target.asset_type.value, valor, label, None)
    for f in findings:
        t = f.target
        valor, kk = _identidade(t.asset_type.value, t.value)
        if kk not in obs or obs[kk][3] is None:
            label = scrub(t.label) if t.label else None
            obs[kk] = (t.asset_type.value, valor, label, f.source_tool)
    return obs


async def registrar_ativos(
    session: AsyncSession,
    scan_id: UUID,
    target: Target,
    findings: list[Finding],
    *,
    scanners_ran: list[str],
) -> dict[str, UUID]:
    """Faz upsert dos ativos vistos no scan e preenche `Finding.asset_id`.

    `scanners_ran` é obrigatório: decide se o alvo do scan conta como visto.

    Dentro da MESMA sessão/transação do `_persist_findings` (o caller comita). Devolve o
    mapa asset_key -> asset_id para quem quiser. Cada finding sai com `asset_id` setado a
    partir do ativo do seu `.target`.
    """
    from orchestrator.persistence.models import AssetObservationRow, AssetRow

    obs = _coletar_observacoes(target, findings, scanners_ran)
    key_to_id: dict[str, UUID] = {}

    def _reaparecer(row: AssetRow, label: str | None) -> AssetRow:
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
            try:
                # Savepoint: se dois workers escaneiam o mesmo host novo, o segundo bate
                # na unique de asset_key. Sem isto o IntegrityError no flush derrubaria o
                # persist inteiro e os findings do scan se perderiam. O savepoint isola a
                # falha; recarrego a linha que o outro worker gravou e sigo.
                #
                # O `add` tem de ficar DENTRO do bloco: `begin_nested()` faz flush do que
                # está pendente ANTES de abrir o savepoint. Com o add do lado de fora, o
                # INSERT corria fora do savepoint e a violação envenenava a transação
                # inteira (PendingRollbackError). Só o Postgres mostrou: o SQLite
                # serializa as escritas e a corrida nunca acontecia lá.
                async with session.begin_nested():
                    novo = AssetRow(
                        asset_key=chave,
                        asset_type=atype,
                        value=value,
                        label=label,
                        last_scan_id=scan_id,
                    )
                    session.add(novo)
                    await session.flush()
                row = novo
            except IntegrityError:
                existente = (
                    await session.exec(select(AssetRow).where(AssetRow.asset_key == chave))
                ).first()
                if existente is None:
                    raise
                row = _reaparecer(existente, label)
        else:
            row = _reaparecer(row, label)
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
        f.asset_id = key_to_id.get(_identidade(f.target.asset_type.value, f.target.value)[1])

    return key_to_id
