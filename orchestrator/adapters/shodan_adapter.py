"""Shodan adapter — query por organização/CIDR pra ver o que está exposto pra internet.

Requer SHODAN_API_KEY. Opcional na fase 2.5.

Silêncio corrigido: em qualquer exceção da busca (cota estourada, chave inválida,
timeout, API fora do ar) o adapter FABRICAVA `{"matches": [], "total": 0}` e o
handle voltava saudável. O relatório de exposição então afirmava que a superfície
externa foi consultada e nada apareceu — para uma consulta que nunca chegou ao
Shodan. Agora a falha vira `ScanIntegrityError` e o vetor entra como não verificado.
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


class ShodanAdapter:
    name = "shodan"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("SHODAN_API_KEY", "")
        self._scans: dict[str, dict[str, Any]] = {}

    async def health(self) -> bool:
        if not self.api_key:
            return False
        try:
            import shodan as _shodan

            api = _shodan.Shodan(self.api_key)
            await asyncio.to_thread(api.info)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("shodan.health_failed", error=str(e))
            return False

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        import shodan as _shodan

        # target.value pode ser query Shodan ("org:Banco X") ou CIDR ("net:200.x/24")
        query = options.get("query") or target.value
        api = _shodan.Shodan(self.api_key)
        try:
            data = await asyncio.to_thread(api.search, query, limit=int(options.get("limit", 100)))
        except Exception as e:  # noqa: BLE001
            log.error("shodan.search_failed", error=str(e))
            raise ScanIntegrityError(
                f"consulta ao Shodan falhou ({type(e).__name__}: {e}). Cota, chave ou "
                "conectividade. NÃO há resultado: zero exposições aqui seria invenção."
            ) from e

        total = int(data.get("total") or 0)
        matches = list(data.get("matches") or [])
        # A API pagina de 100 em 100. Quando `total` supera o que veio, o resto da
        # superfície exposta NÃO foi olhada — e um relatório que omite isso deixa o
        # leitor concluir que viu tudo.
        gaps: list[str] = []
        if total > len(matches):
            gaps.append(
                f"o Shodan reporta {total} resultado(s) para esta consulta e só "
                f"{len(matches)} foram lidos (limite da pagina): o restante da "
                "superficie exposta nao foi analisado."
            )

        native_id = str(uuid4())
        self._scans[native_id] = {"query": query, "matches": matches, "gaps": gaps}
        return ScanHandle(
            adapter=self.name,
            native_id=native_id,
            metadata={"query": query, "total": total, "lidos": len(matches)},
        )

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        return ScanStatus.DONE if handle.native_id in self._scans else ScanStatus.FAILED

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        dados = self._scans.get(handle.native_id)
        if dados is None:
            raise ScanIntegrityError("shodan: handle desconhecido, a consulta não rodou.")
        return RawResults(
            adapter=self.name,
            payload=dados,
            coverage_gaps=list(dados.get("gaps") or []),
        )

    async def normalize(self, raw: RawResults) -> list[Finding]:
        findings: list[Finding] = []
        placeholder = uuid4()
        for m in raw.payload.get("matches", []):
            ip = m.get("ip_str", "?")
            port = m.get("port", "?")
            product = m.get("product", "unknown")
            vulns = list((m.get("vulns") or {}).keys())  # CVEs
            target = Target(
                asset_type=AssetType.HOST,
                value=f"{ip}:{port}",
                label=product,
            )
            sev = Severity.MEDIUM
            if vulns:
                sev = Severity.HIGH

            cve_id = vulns[0] if vulns else None
            findings.append(
                Finding(
                    scan_id=placeholder,
                    target=target,
                    source_tool=self.name,
                    source_rule_id=f"shodan-{product}",
                    vuln_id=cve_id,
                    title=f"Exposição Shodan: {product} em {ip}:{port}",
                    description=(
                        f"{product} v{m.get('version', '?')} exposto.\n"
                        f"Organização: {m.get('org')}, ASN: {m.get('asn')}, "
                        f"País: {m.get('location', {}).get('country_name')}\n"
                        f"CVEs: {', '.join(vulns) if vulns else 'nenhum reportado'}"
                    ),
                    severity=sev,
                    confidence=Confidence.FIRM,
                    evidence=[
                        Evidence(
                            description=f"banner: {(m.get('data') or '')[:300]}",
                            snippet=m.get("hostnames", [None])[0] if m.get("hostnames") else None,
                        )
                    ],
                )
            )
        log.info("shodan.normalize_done", findings=len(findings))
        return findings
