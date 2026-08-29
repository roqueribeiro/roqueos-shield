"""Censys adapter — alternativa ao Shodan pra exposição de internet.

Requer pacote `censys` opcional. Opt-in.

Três silêncios corrigidos aqui, todos da mesma família:

1. `_run` engolia a exceção da busca e devolvia a lista como se estivesse completa —
   credencial errada virava "nada exposto".
2. Erro no meio da paginação devolvia resultado PARCIAL como se fosse total: o
   relatório mostrava a primeira página e omitia que as outras não vieram.
3. `health()` só CONSTRUÍA o cliente, sem nenhuma ida à API. Chave inválida passava
   no health, a busca falhava depois, e o vetor sumia sem registro.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import uuid4

import structlog

from orchestrator.adapters.base import ScanIntegrityError
from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Evidence,
    Finding,
    RawResults,
    ScanHandle,
    ScanStatus,
    Severity,
    Target,
)

log = structlog.get_logger(__name__)


class CensysAdapter:
    name = "censys"

    def __init__(self, api_id: str | None = None, api_secret: str | None = None) -> None:
        self.api_id = api_id or os.environ.get("CENSYS_API_ID", "")
        self.api_secret = api_secret or os.environ.get("CENSYS_API_SECRET", "")
        self._scans: dict[str, dict[str, Any]] = {}

    async def health(self) -> bool:
        """Health COM ida à API. Construir o cliente não prova nada.

        O construtor do SDK não faz round-trip: com uma chave inválida ele retorna um
        objeto perfeitamente saudável. O health precisa de uma chamada real, senão
        aprova credencial quebrada e o erro só aparece na busca — onde antes era
        engolido.
        """
        if not (self.api_id and self.api_secret):
            return False
        try:
            from censys.search import CensysHosts  # type: ignore[import-not-found]

            cliente = CensysHosts(api_id=self.api_id, api_secret=self.api_secret)
            conta = getattr(cliente, "account", None)
            if callable(conta):
                await asyncio.to_thread(conta)
                return True
            # SDK sem `account()`: faz a busca mais barata possível como round-trip.
            await asyncio.to_thread(lambda: next(iter(cliente.search("ip:1.1.1.1", per_page=1))))
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("censys.health_failed", error=str(e))
            return False

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        from censys.search import CensysHosts  # type: ignore[import-not-found]

        query = options.get("query") or target.value
        hosts = CensysHosts(api_id=self.api_id, api_secret=self.api_secret)

        pedidas = int(options.get("pages", 1))

        def _run() -> tuple[list[dict[str, Any]], int, str]:
            """(resultados, páginas lidas, erro). O erro NÃO é engolido."""
            results: list[dict[str, Any]] = []
            lidas = 0
            try:
                for page in hosts.search(query, per_page=100, pages=pedidas):
                    results.extend(page)
                    lidas += 1
            except Exception as e:  # noqa: BLE001
                log.error("censys.search_failed", error=str(e), paginas_lidas=lidas)
                return results, lidas, f"{type(e).__name__}: {e}"
            return results, lidas, ""

        results, lidas, erro = await asyncio.to_thread(_run)
        if erro and not results:
            raise ScanIntegrityError(
                f"consulta ao Censys falhou sem devolver nada ({erro}). Zero exposições "
                "aqui seria invenção: a superfície externa não foi consultada."
            )
        gaps: list[str] = []
        if erro:
            gaps.append(
                f"a consulta ao Censys parou no meio depois de {lidas} de {pedidas} "
                f"página(s) ({erro}): parte da superfície exposta não foi analisada."
            )

        native_id = str(uuid4())
        self._scans[native_id] = {"query": query, "results": results, "gaps": gaps}
        return ScanHandle(
            adapter=self.name,
            native_id=native_id,
            metadata={"query": query, "count": len(results), "paginas": lidas},
        )

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        return ScanStatus.DONE if handle.native_id in self._scans else ScanStatus.FAILED

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        dados = self._scans.get(handle.native_id)
        if dados is None:
            raise ScanIntegrityError("censys: handle desconhecido, a consulta não rodou.")
        return RawResults(
            adapter=self.name,
            payload=dados,
            coverage_gaps=list(dados.get("gaps") or []),
        )

    async def normalize(self, raw: RawResults) -> list[Finding]:
        findings: list[Finding] = []
        placeholder = uuid4()
        for h in raw.payload.get("results", []):
            ip = h.get("ip", "?")
            services = h.get("services") or []
            for svc in services:
                port = svc.get("port", "?")
                proto = svc.get("transport_protocol", "tcp").lower()
                target_obj = Target(
                    asset_type=AssetType.HOST,
                    value=f"{ip}:{port}/{proto}",
                    label=svc.get("service_name", "unknown"),
                )
                findings.append(
                    Finding(
                        scan_id=placeholder,
                        target=target_obj,
                        source_tool=self.name,
                        source_rule_id=svc.get("service_name", "unknown"),
                        title=f"Censys exposure: {svc.get('service_name')} em {ip}:{port}",
                        description=(
                            f"Serviço {svc.get('service_name')} em {ip}:{port}/{proto}. "
                            f"Software: {svc.get('software', [])}"
                        ),
                        severity=Severity.MEDIUM,
                        confidence=Confidence.FIRM,
                        evidence=[Evidence(description=f"banner em port {port}")],
                    )
                )
        log.info("censys.normalize_done", findings=len(findings))
        return findings
