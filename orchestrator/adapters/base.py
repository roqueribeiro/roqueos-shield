"""ScannerAdapter contract — every integration implements this Protocol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.schemas import (
    Confidence,
    Evidence,
    Finding,
    RawResults,
    ScanHandle,
    ScanStatus,
    Severity,
    Target,
)


class ScanIntegrityError(RuntimeError):
    """O scanner terminou, mas o resultado não é confiável.

    Existe para separar "rodou e não achou" de "não deu para verificar". Um arquivo
    de saída ausente, um XML que não parseia, uma ferramenta que não avaliou nenhum
    controle: nada disso é alvo limpo, e devolver lista vazia nesses casos faz a
    ferramenta mentir sem querer. O pipeline transforma esta exceção em cobertura
    incompleta declarada.
    """


@runtime_checkable
class ScannerAdapter(Protocol):
    """Contrato uniforme para todo scanner.

    Vida de uma varredura:
        h = await adapter.start_scan(target, options)
        while (s := await adapter.poll(h)) == ScanStatus.RUNNING:
            await asyncio.sleep(...)
        if s == ScanStatus.DONE:
            raw = await adapter.fetch_results(h)
            findings = await adapter.normalize(raw)
    """

    name: str

    async def health(self) -> bool:
        """True se o backend (daemon, API) está respondendo."""
        ...

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        """Dispara varredura. Não bloqueia — retorna handle pra polling."""
        ...

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        """Estado atual da varredura."""
        ...

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        """Saída bruta. Só chamado quando poll() retorna DONE."""
        ...

    async def normalize(self, raw: RawResults) -> list[Finding]:
        """Converte saída bruta em Findings canônicos."""
        ...


def read_jsonl(
    path: Path,
    *,
    adapter: str,
    gaps: list[str],
) -> list[dict[str, Any]]:
    """Lê saída JSONL (nuclei, trufflehog, dnstwist...) SEM perder linha em silêncio.

    O padrão anterior era `except json.JSONDecodeError: continue` em cinco adapters.
    Numa ferramenta de segurança, descartar evidência sem avisar é o mesmo defeito
    do resto deste repo: o relatório fica com menos achados e ninguém sabe por quê.

    Regra:
      - nenhuma linha boa e alguma ruim → `ScanIntegrityError` (saída é lixo);
      - alguma boa e alguma ruim → devolve as boas e registra a lacuna em `gaps`,
        que o pipeline transforma em achado INFO visível.
    """
    itens: list[dict[str, Any]] = []
    ruins = 0
    if not path.exists():
        return itens
    for linha in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linha.strip():
            continue
        try:
            obj = json.loads(linha)
        except json.JSONDecodeError:
            ruins += 1
            continue
        if isinstance(obj, dict):
            itens.append(obj)
        else:
            ruins += 1
    if ruins and not itens:
        raise ScanIntegrityError(
            f"{adapter}: as {ruins} linha(s) de saída são ilegíveis — saída truncada, "
            "processo morto no meio, ou formato mudou de versão. Zero achados aqui não "
            "é alvo limpo."
        )
    if ruins:
        gaps.append(
            f"{ruins} linha(s) da saída do {adapter} não puderam ser lidas e foram "
            "descartadas: pode haver achado a menos neste relatório."
        )
    return itens


def coverage_gap_finding(
    *,
    adapter: str,
    gaps: list[str],
    scan_id: UUID,
    target: Target,
) -> Finding:
    """Transforma lacunas de cobertura num achado INFO — o mecanismo da regra.

    "Avisar no log" não é controle: ninguém abre o log do worker. Um achado INFO
    entra no relatório, no bundle e na tela, junto do resto.
    """
    return Finding(
        scan_id=scan_id,
        target=target,
        source_tool=adapter,
        source_rule_id=f"{adapter}-coverage-gap",
        title=f"Cobertura incompleta em {adapter}",
        description=(
            "Este scanner rodou, mas parte do alvo ficou sem verificação. "
            "A ausência de achados nessa parte NÃO indica ausência de problema.\n\n- "
            + "\n- ".join(gaps)
        ),
        severity=Severity.INFO,
        confidence=Confidence.CERTAIN,
        evidence=[Evidence(description=g) for g in gaps[:5]],
        remediation="Corrija a causa da lacuna e rode de novo para ter cobertura completa.",
    )
