"""ScannerAdapter contract — every integration implements this Protocol."""


from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from orchestrator.domain.schemas import (
    Finding,
    RawResults,
    ScanHandle,
    ScanStatus,
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
