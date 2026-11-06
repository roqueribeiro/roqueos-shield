"""OWASP ZAP adapter — drives ZAP daemon via HTTP API.

Fases: traditional spider, AJAX spider (opt-in), active scan (opt-in), passive scan.

- `options['active']=True` liga o active scan (injeta payloads reais; blast radius maior).
- `options['ajax']=True` liga o AJAX spider, que sobe um browser headless pra descobrir
  rotas que o spider tradicional não enxerga numa aplicação 100% JavaScript (Juice Shop,
  e a maioria dos apps Angular/React/Vue). Sem ele, o active scan não tem o que atacar
  numa SPA e o relatório sai vazio SEM a aplicação ter sido de fato percorrida.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
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


_ZAP_RISK_TO_SEVERITY: dict[str, Severity] = {
    "Informational": Severity.INFO,
    "Low": Severity.LOW,
    "Medium": Severity.MEDIUM,
    "High": Severity.HIGH,
    # ZAP usa "High" como teto; CVEs com CVSS critical são marcadas via plugin.
}

_ZAP_CONFIDENCE: dict[str, Confidence] = {
    "False Positive": Confidence.TENTATIVE,
    "Low": Confidence.TENTATIVE,
    "Medium": Confidence.FIRM,
    "High": Confidence.FIRM,
    "Confirmed": Confidence.CERTAIN,
}


class ZAPAdapter:
    """Cliente assíncrono pra ZAP daemon API."""

    name = "zap"

    def __init__(self, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        # 60s (e não 30): sob o AJAX spider crawleando uma SPA grande, o thread da API
        # do daemon satura e as chamadas de status demoram. O poll ainda tolera timeout.
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)
        # mapa: native_id -> {"spider_id": ..., "ascan_id": ..., "url": ..., "active": bool}
        self._scans: dict[str, dict[str, Any]] = {}

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        params.setdefault("apikey", self.api_key)
        r = await self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def health(self) -> bool:
        try:
            data = await self._get("/JSON/core/view/version/")
            return "version" in data
        except Exception as e:  # noqa: BLE001
            log.warning("zap.health_failed", error=str(e))
            return False

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        if target.asset_type not in (AssetType.URL, AssetType.HOST, AssetType.DOMAIN):
            raise ValueError(f"zap não suporta asset_type={target.asset_type}")

        url = self._ensure_url(target.value)
        active = bool(options.get("active", False))
        ajax = bool(options.get("ajax", False))
        max_children = options.get("max_children", "10")
        headers = options.get("headers") or {}
        openapi_url = options.get("openapi_url")

        # Authenticated scanning: inject the auth headers into EVERY request via
        # ZAP's replacer so the spider + active scan reach behind-login surfaces.
        # Best-effort: the value goes only to ZAP (never logged/persisted), and a
        # missing replacer add-on must NOT fail the scan.
        for name, value in headers.items():
            try:
                await self._get(
                    "/JSON/replacer/action/addRule/",
                    description=f"cai-auth-{name}",
                    enabled="true",
                    matchType="REQ_HEADER",
                    matchString=name,
                    matchRegex="false",
                    replacement=value,
                )
            except Exception as e:  # noqa: BLE001 — degrade gracefully (no add-on)
                log.warning("zap.replacer_failed", header=name, error=str(e))
        if headers:
            # log the header NAMES only — never the secret values.
            log.info("zap.auth_headers_applied", headers=sorted(headers.keys()))

        # OpenAPI/Swagger import: enumerate the real API surface (not just crawled
        # links) so the scan tests the documented endpoints.
        if openapi_url:
            try:
                await self._get(
                    "/JSON/openapi/action/importUrl/", url=openapi_url, hostOverride=url
                )
                log.info("zap.openapi_imported", spec=openapi_url)
            except Exception as e:  # noqa: BLE001
                log.warning("zap.openapi_import_failed", error=str(e))

        # 1. acessa a URL pra registrar no site tree
        await self._acessar_alvo(url)

        # 2. spider — com retry se ZAP retornar scan_id inválido (bug pós newSession)
        spider_id = await self._start_spider_with_retry(url, max_children)
        log.info("zap.spider_started", scan_id=spider_id, url=url)

        native_id = str(uuid4())
        self._scans[native_id] = {
            "spider_id": spider_id,
            "ascan_id": None,
            "url": url,
            "active": active,
            "ajax": ajax,
            "phase": "spider",
            "gaps": [],
        }

        return ScanHandle(
            adapter=self.name,
            native_id=native_id,
            metadata={"url": url, "active": active, "ajax": ajax, "spider_id": spider_id},
        )

    async def _acessar_alvo(self, url: str) -> None:
        """Registra a URL na árvore do ZAP, com uma segunda tentativa.

        O ZAP responde 500 no `accessUrl` quando ELE não alcança o alvo (DNS, TLS,
        conexão recusada, alvo lento). Em produção isso subia como traceback de
        `adapter.crashed`. Uma falha passageira ganha mais uma chance; duas seguidas
        viram ScanIntegrityError com o motivo, e o pipeline declara a cobertura
        incompleta em vez de um crash.
        """
        ultimo_erro: Exception | None = None
        for tentativa in (1, 2):
            try:
                await self._get("/JSON/core/action/accessUrl/", url=url, followRedirects="true")
                return
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500:
                    raise
                ultimo_erro = e
            except httpx.TransportError as e:
                ultimo_erro = e
            log.warning(
                "zap.access_url_failed", url=url, tentativa=tentativa, error=str(ultimo_erro)
            )
        raise ScanIntegrityError(
            f"zap não alcançou {url} (accessUrl falhou duas vezes: {ultimo_erro}). "
            "O alvo pode estar fora do ar ou bloqueado para o container do ZAP; "
            "o scan NÃO verificou este vetor."
        )

    async def _start_spider_with_retry(self, url: str, max_children: Any) -> str:
        """Inicia spider e valida que ZAP devolveu scan_id válido (>0).

        Quirk conhecido: após `newSession`, primeiro spider call pode retornar
        `{"scan": "0"}` que depois falha com 400 no poll. Fazemos 1 retry.
        """
        for attempt in (1, 2):
            spider = await self._get(
                "/JSON/spider/action/scan/",
                url=url,
                maxChildren=str(max_children),
                recurse="true",
            )
            spider_id = str(spider.get("scan", ""))
            if spider_id.isdigit() and int(spider_id) > 0:
                return spider_id
            log.warning(
                "zap.spider_id_invalid",
                got=spider_id,
                attempt=attempt,
                url=url,
            )
            if attempt == 1:
                # re-acessa URL pra resetar estado interno do ZAP e tenta de novo
                await self._acessar_alvo(url)
        raise RuntimeError(
            f"ZAP returned invalid spider scan_id after retry (got {spider_id!r}); "
            "verifique se o daemon não foi reiniciado / sessão corrompida"
        )

    async def _iniciar_ativo_ou_passivo(self, state: dict[str, Any]) -> ScanStatus:
        """Depois da descoberta (spider + ajax): dispara o active scan, ou vai esperar a
        fila passiva. Um lugar só decide, chamado pelo fim do spider e pelo fim do ajax.

        O active scan tem o MESMO retry do spider pro quirk do `scan="0"`: logo depois do
        AJAX spider, com o browser headless ainda liberando memória, o ZAP devolve "0" pra
        ação de ascan uma vez e aceita na segunda. Sem o retry, o scan morria aqui com
        `ascan_id_invalid` num alvo que ia ser varrido sem problema 5s depois (um FAILED
        que não era do alvo, era do timing). Duas recusas seguidas aí sim é FAILED de
        verdade (contrato do silêncio: vetor NÃO verificado, nunca "limpo" calado)."""
        if not state["active"]:
            state["phase"] = "passive_wait"
            return ScanStatus.RUNNING
        ascan_id = ""
        for attempt in (1, 2):
            ascan = await self._get(
                "/JSON/ascan/action/scan/", url=state["url"], recurse="true"
            )
            ascan_id = str(ascan.get("scan", ""))
            if ascan_id.isdigit() and int(ascan_id) >= 1:
                state["ascan_id"] = ascan_id
                state["phase"] = "ascan"
                log.info("zap.ascan_started", scan_id=state["ascan_id"])
                return ScanStatus.RUNNING
            log.warning("zap.ascan_id_invalid", got=ascan_id, attempt=attempt)
            if attempt == 1:
                await self._acessar_alvo(state["url"])  # reseta o estado interno do ZAP
        log.error("zap.ascan_failed", got=ascan_id)
        return ScanStatus.FAILED

    async def _start_ajax(self, state: dict[str, Any]) -> ScanStatus:
        """Dispara o AJAX spider (browser headless) pra percorrer uma SPA.

        Antes de iniciar, limita o footprint do crawl: quantos browsers headless sobem, a
        profundidade, quantos estados da SPA visitar e por quanto tempo. O motivo é
        memória. O default do AJAX spider é UM browser por core (8+ Firefox num Mac) e
        espaço de estados ILIMITADO: o Crawljax renderiza estado após estado e a árvore de
        processos do Firefox cresce sem teto até estourar a RAM da VM do Docker, e o
        container do ZAP morre por OOM (exit 137) no meio do crawl. Do lado do poll isso
        chegava como timeout persistente e derrubava o scan (o alvo parecia "não
        verificado" sem que a causa fosse óbvia). Um crawler de SPA sem teto estoura
        QUALQUER caixa de memória fixa; o teto de profundidade, de estados e de tempo é o
        que segura o pico, não o número de browsers sozinho (o Firefox acumula memória por
        estado renderizado, ~20 MB/s numa SPA grande, e um crawl longo rasteja até o teto
        da VM). Os limites default (profundidade 4, 25 estados, 3 min) alcançam as rotas do
        Juice Shop e cia. sem varrer a SPA inteira, e cabem numa VM de 8 GB. Ambiente com
        mais RAM afrouxa via options. O ajuste é best-effort: add-on antigo que não conhece
        a opção vira aviso, nunca falha o scan (o crawl ainda roda, só sem aquele teto).

        Se o add-on `spiderAjax` não estiver na imagem do ZAP, iniciar falha. Isso NÃO
        pode virar scan "limpo" calado numa SPA: a recusa vira lacuna de cobertura
        declarada e o scan segue pro active/passive com o aviso preservado no relatório.
        """
        for opcao, valor in (
            ("setOptionNumberOfBrowsers", str(state.get("ajax_browsers", 1))),
            ("setOptionMaxCrawlDepth", str(state.get("ajax_max_depth", 4))),
            ("setOptionMaxCrawlStates", str(state.get("ajax_max_states", 25))),
            ("setOptionMaxDuration", str(state.get("ajax_max_duration_min", 3))),
        ):
            try:
                await self._get(f"/JSON/ajaxSpider/action/{opcao}/", Integer=valor)
            except Exception as e:  # noqa: BLE001  (teto de recurso é best-effort)
                log.warning("zap.ajax_option_failed", opcao=opcao, valor=valor, error=str(e))
        try:
            await self._get(
                "/JSON/ajaxSpider/action/scan/",
                url=state["url"],
                inScope="false",
                subtreeOnly="false",
            )
        except Exception as e:  # noqa: BLE001
            gaps = state.setdefault("gaps", [])
            gaps.append(
                "o AJAX spider foi solicitado mas o ZAP recusou iniciá-lo "
                f"({e}); numa aplicação 100% JavaScript (SPA) as rotas podem não ter sido "
                "percorridas e os alertas abaixo podem estar incompletos. Verifique se o "
                "add-on 'spiderAjax' está presente na imagem do ZAP."
            )
            log.warning("zap.ajax_unavailable", error=str(e))
            return await self._iniciar_ativo_ou_passivo(state)
        state["phase"] = "ajax"
        log.info("zap.ajax_started", url=state["url"])
        return ScanStatus.RUNNING

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        state = self._scans.get(handle.native_id)
        if state is None:
            return ScanStatus.FAILED

        try:
            if state["phase"] == "spider":
                s = await self._get("/JSON/spider/view/status/", scanId=str(state["spider_id"]))
                state["poll_errors"] = 0  # o daemon respondeu: zera a sequência de soluços
                progress = int(s.get("status", "0"))
                if progress >= 100:
                    # SPA (Angular/React/Vue): o spider tradicional mal enxerga rotas, então
                    # o AJAX spider roda ANTES do active scan pra povoar a árvore com as URLs
                    # que só aparecem via JS. Sem isto o active não tem o que atacar e o
                    # relatório sai "limpo" numa app vulnerável.
                    if state.get("ajax"):
                        return await self._start_ajax(state)
                    return await self._iniciar_ativo_ou_passivo(state)
                return ScanStatus.RUNNING

            if state["phase"] == "ajax":
                # o AJAX spider reporta "running"/"stopped", não porcentagem.
                s = await self._get("/JSON/ajaxSpider/view/status/")
                state["poll_errors"] = 0  # respondeu: zera a sequência de soluços
                if str(s.get("status", "running")).lower() == "stopped":
                    return await self._iniciar_ativo_ou_passivo(state)
                return ScanStatus.RUNNING

            if state["phase"] == "ascan":
                s = await self._get("/JSON/ascan/view/status/", scanId=str(state["ascan_id"]))
                state["poll_errors"] = 0  # respondeu: zera a sequência de soluços
                progress = int(s.get("status", "0"))
                if progress >= 100:
                    state["phase"] = "passive_wait"
                    return ScanStatus.RUNNING
                return ScanStatus.RUNNING

            if state["phase"] == "passive_wait":
                # passive scan roda em background; espera fila zerar.
                # ATENÇÃO: fila vazia NÃO prova que houve varredura. Se o spider não
                # rastreou nada (alvo fora do ar, bloqueio por robots.txt, app 100%
                # JS sem o ajax spider), a fila já nasce zerada e o scan fecharia
                # "limpo" sem ter visitado uma única URL. Por isso conta as URLs.
                pscan = await self._get("/JSON/pscan/view/recordsToScan/")
                state["poll_errors"] = 0  # respondeu: zera a sequência de soluços
                records = int(pscan.get("recordsToScan", "0"))
                if records == 0:
                    state["urls_rastreadas"] = await self._contar_urls(state["url"])
                    state["phase"] = "done"
                    return ScanStatus.DONE
                return ScanStatus.RUNNING

            if state["phase"] == "done":
                return ScanStatus.DONE

        except (httpx.TimeoutException, httpx.TransportError) as e:
            # ZAP fica instável sob carga: o AJAX spider numa SPA satura o thread da API do
            # daemon (timeout) e a pressão de memória faz o DNS do Docker oscilar (name
            # resolution). Um soluço isolado NÃO é "scan falhou": conta os CONSECUTIVOS e
            # tolera alguns; qualquer poll que volta a responder zera o contador (nas fases
            # acima), então isto é streak de verdade, não soma do scan inteiro. Só reprova
            # se o daemon ficar mudo de fato. É espera contada, não silêncio.
            state["poll_errors"] = state.get("poll_errors", 0) + 1
            log.warning(
                "zap.poll_transiente",
                error=str(e) or type(e).__name__,
                phase=state.get("phase"),
                consecutivos=state["poll_errors"],
            )
            if state["poll_errors"] >= 12:
                log.error(
                    "zap.poll_failed",
                    error="ZAP parou de responder (timeouts persistentes)",
                    phase=state.get("phase"),
                )
                return ScanStatus.FAILED
            return ScanStatus.RUNNING
        except Exception as e:  # noqa: BLE001
            log.error("zap.poll_failed", error=str(e), phase=state.get("phase"))
            return ScanStatus.FAILED

        return ScanStatus.RUNNING

    async def _contar_urls(self, base: str) -> int:
        """Quantas URLs o ZAP conhece sob a base. Zero = nada foi rastreado."""
        try:
            dados = await self._get("/JSON/core/view/urls/", baseurl=base)
            return len(dados.get("urls") or [])
        except Exception as e:  # noqa: BLE001
            log.warning("zap.urls_count_failed", error=str(e))
            return -1  # desconhecido: nao afirma nem que rastreou nem que nao

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        state = self._scans[handle.native_id]

        rastreadas = state.get("urls_rastreadas")
        if rastreadas is None:
            rastreadas = await self._contar_urls(state["url"])
        if rastreadas == 0:
            raise ScanIntegrityError(
                "o ZAP não rastreou NENHUMA URL sob o alvo: nada foi verificado. "
                "Causas típicas: alvo fora do ar, bloqueio por robots.txt, WAF, ou "
                "aplicação 100% JavaScript (precisa do ajax spider). Zero alertas "
                "aqui NÃO significa aplicação segura."
            )

        # Paginação. Antes era UMA página de 500 alertas, sem `start` seguinte: numa
        # aplicação grande o excedente sumia do relatório sem aviso.
        pagina = 500
        teto = int(state.get("max_alerts", 10000))
        alertas: list[dict[str, Any]] = []
        # lacunas acumuladas durante o scan (ex.: AJAX spider indisponível) entram antes
        # das detectadas aqui, pra não sumirem do relatório.
        gaps: list[str] = list(state.get("gaps", []))
        if rastreadas < 0:
            # `-1` = não deu para contar (o daemon recusou a chamada). O comentário do
            # `_contar_urls` está certo em não AFIRMAR que rastreou — mas seguir em
            # frente calado desliga a guarda inteira. Justo quando o daemon está sob
            # carga e a aplicação é 100% JS, o resultado sairia como app segura.
            gaps.append(
                "não foi possível confirmar quantas URLs o ZAP rastreou (o daemon "
                "recusou a consulta): não dá para afirmar que a aplicação foi de fato "
                "percorrida antes destes alertas."
            )
        truncou = False
        while True:
            lote = await self._get(
                "/JSON/core/view/alerts/",
                baseurl=state["url"],
                start=str(len(alertas)),
                count=str(pagina),
            )
            itens = lote.get("alerts") or []
            alertas.extend(itens)
            if len(itens) < pagina:
                break
            if len(alertas) >= teto:
                truncou = True
                break
        if truncou:
            gaps.append(
                f"o ZAP devolveu o teto de {teto} alertas e a leitura foi interrompida: "
                "pode haver mais achados não listados."
            )

        # `baseurl` filtra por PREFIXO. Se a aplicação redireciona para outro host ou
        # esquema (http -> https, apex -> www), os alertas do destino ficam de fora do
        # filtro e o relatório some com eles. Comparar com o total sem filtro não
        # custa nada e denuncia a diferença.
        try:
            resumo = await self._get("/JSON/alert/view/alertCountsByRisk/")
            total_geral = sum(int(v) for v in (resumo or {}).values() if str(v).isdigit())
            if total_geral > len(alertas) and not truncou:
                gaps.append(
                    f"o ZAP tem {total_geral} alerta(s) na sessão mas só {len(alertas)} "
                    f"casam com o prefixo {state['url']} — tipicamente redirecionamento "
                    "para outro host/esquema. Os demais não entraram neste relatório."
                )
        except Exception as e:  # noqa: BLE001
            log.warning("zap.alert_counts_failed", error=str(e))

        log.info(
            "zap.fetch_ok",
            alertas=len(alertas),
            urls_rastreadas=rastreadas,
            truncou=truncou,
        )
        return RawResults(
            adapter=self.name,
            payload={"alerts": alertas},
            coverage_gaps=gaps,
        )

    async def normalize(self, raw: RawResults) -> list[Finding]:
        findings: list[Finding] = []
        placeholder_scan_id = uuid4()

        alerts = raw.payload.get("alerts", [])
        for a in alerts:
            risk = a.get("risk", "Low")
            confidence_str = a.get("confidence", "Medium")
            severity = _ZAP_RISK_TO_SEVERITY.get(risk, Severity.LOW)
            confidence = _ZAP_CONFIDENCE.get(confidence_str, Confidence.FIRM)

            url = a.get("url", "")
            target = (
                Target(asset_type=AssetType.URL, value=url)
                if url
                else Target(asset_type=AssetType.URL, value="unknown")
            )

            cwe_id = a.get("cweid")
            cwe = [f"CWE-{cwe_id}"] if cwe_id and cwe_id != "-1" else []

            findings.append(
                Finding(
                    scan_id=placeholder_scan_id,
                    target=target,
                    source_tool=self.name,
                    source_rule_id=str(a.get("pluginId", a.get("alertRef", ""))),
                    # O ZAP alerta por PARÂMETRO: XSS em `?q=` e em `?sort=` da mesma
                    # URL têm o mesmo pluginId e o mesmo target.value. Sem isto a
                    # chave de dedupe colidia e um dos dois sumia do relatório.
                    dedup_discriminator=(a.get("param") or None),
                    cwe=cwe,
                    title=a.get("name", "ZAP alert"),
                    description=a.get("description", ""),
                    severity=severity,
                    confidence=confidence,
                    evidence=[
                        Evidence(
                            description=a.get("evidence", "(sem evidência adicional)"),
                            request=a.get("request"),
                            response=a.get("response"),
                            payload=a.get("attack"),
                            snippet=a.get("evidence"),
                        )
                    ],
                    remediation=a.get("solution") or None,
                    references=self._parse_refs(a.get("reference", "")),
                )
            )

        log.info("zap.normalize_done", findings=len(findings))
        return findings

    @staticmethod
    def _ensure_url(value: str) -> str:
        if value.startswith(("http://", "https://")):
            return value
        return f"http://{value}"

    @staticmethod
    def _parse_refs(text: str) -> list[Any]:
        from pydantic import HttpUrl, TypeAdapter

        if not text:
            return []
        urls = [
            u.strip() for u in text.split("\n") if u.strip().startswith(("http://", "https://"))
        ]
        adapter = TypeAdapter(HttpUrl)
        out: list[Any] = []
        for u in urls:
            try:
                out.append(adapter.validate_python(u))
            except Exception:  # noqa: BLE001  silencio-ok: URL de REFERÊNCIA malformada
                # Não é achado nem evidência — é o link "leia mais" que o ZAP anexa
                # ao alerta. Descartar um link quebrado não esconde vulnerabilidade
                # nenhuma; o alerta em si continua inteiro.
                continue
        return out

    async def aclose(self) -> None:
        await self._client.aclose()
