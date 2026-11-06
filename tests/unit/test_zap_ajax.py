"""AJAX spider: a fase que faz o scan achar algo numa SPA (Juice Shop e cia.).

O spider tradicional não enxerga rotas numa aplicação 100% JavaScript, então o active
scan não tinha o que atacar e o relatório saía vazio numa app cheia de buraco. Estes
testes provam quatro coisas:

1. com `ajax=True`, o AJAX spider roda ENTRE o spider e o active scan;
2. com `ajax=True` e sem active, o ajax roda e o scan vai pro passivo;
3. se o add-on do ajax não está na imagem, a recusa vira LACUNA declarada e o scan
   segue, nunca um "limpo" calado;
4. sem `ajax`, o fluxo antigo (spider -> active/passive) continua intacto.
"""

from __future__ import annotations

from typing import Any

import httpx

from orchestrator.adapters.zap_adapter import ZAPAdapter
from orchestrator.domain.schemas import AssetType, ScanStatus, Target

_ALVO = Target(asset_type=AssetType.URL, value="http://juice-shop:3000")


class _ZapComAjax:
    """ZAP falso com estado, cobrindo spider + ajax spider + ascan + fila passiva."""

    def __init__(
        self,
        *,
        ajax_falha: bool = False,
        ajax_status: tuple[str, ...] = ("running", "stopped"),
        alertas: list[dict[str, Any]] | None = None,
        urls: int = 3,
    ) -> None:
        self.ajax_falha = ajax_falha
        self._ajax_status = iter(ajax_status)
        self.alertas = alertas or []
        self.urls = urls
        self.chamadas: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        p, q = request.url.path, request.url.params
        self.chamadas.append(p)
        if p == "/JSON/spider/action/scan/":
            return httpx.Response(200, json={"scan": "1"})
        if p == "/JSON/spider/view/status/":
            return httpx.Response(200, json={"status": "100"})
        if p == "/JSON/ajaxSpider/action/scan/":
            if self.ajax_falha:
                return httpx.Response(500, json={})
            return httpx.Response(200, json={"scan": "OK"})
        if p == "/JSON/ajaxSpider/view/status/":
            return httpx.Response(200, json={"status": next(self._ajax_status, "stopped")})
        if p == "/JSON/ascan/action/scan/":
            return httpx.Response(200, json={"scan": "2"})
        if p == "/JSON/ascan/view/status/":
            return httpx.Response(200, json={"status": "100"})
        if p == "/JSON/pscan/view/recordsToScan/":
            return httpx.Response(200, json={"recordsToScan": "0"})
        if p == "/JSON/core/view/urls/":
            return httpx.Response(200, json={"urls": [f"u{i}" for i in range(self.urls)]})
        if p == "/JSON/core/view/alerts/":
            inicio, quantos = int(q["start"]), int(q["count"])
            return httpx.Response(200, json={"alerts": self.alertas[inicio : inicio + quantos]})
        if p == "/JSON/alert/view/alertCountsByRisk/":
            return httpx.Response(200, json={"High": str(len(self.alertas))})
        return httpx.Response(200, json={})


def _adapter_com(zap: _ZapComAjax) -> ZAPAdapter:
    adapter = ZAPAdapter(base_url="http://zap:8090", api_key="k")
    adapter._client = httpx.AsyncClient(
        base_url="http://zap:8090", transport=httpx.MockTransport(zap)
    )
    return adapter


async def _rodar(adapter: ZAPAdapter, options: dict[str, Any]):
    handle = await adapter.start_scan(_ALVO, options)
    estados: list[ScanStatus] = []
    for _ in range(8):
        estados.append(await adapter.poll(handle))
        if estados[-1] in (ScanStatus.DONE, ScanStatus.FAILED):
            break
    return handle, estados


async def test_ajax_roda_entre_o_spider_e_o_active_scan() -> None:
    zap = _ZapComAjax()
    adapter = _adapter_com(zap)
    handle, estados = await _rodar(adapter, {"active": True, "ajax": True})

    assert estados[-1] == ScanStatus.DONE
    # o ajax rodou e terminou ANTES do active scan começar
    assert "/JSON/ajaxSpider/action/scan/" in zap.chamadas
    assert "/JSON/ajaxSpider/view/status/" in zap.chamadas
    assert "/JSON/ascan/action/scan/" in zap.chamadas
    assert zap.chamadas.index("/JSON/ajaxSpider/action/scan/") < zap.chamadas.index(
        "/JSON/ascan/action/scan/"
    )
    assert handle.metadata["ajax"] is True


async def test_ajax_sem_active_vai_pro_passivo_sem_disparar_ascan() -> None:
    zap = _ZapComAjax()
    adapter = _adapter_com(zap)
    _, estados = await _rodar(adapter, {"active": False, "ajax": True})

    assert estados[-1] == ScanStatus.DONE
    assert "/JSON/ajaxSpider/action/scan/" in zap.chamadas
    assert "/JSON/ascan/action/scan/" not in zap.chamadas


async def test_ajax_indisponivel_vira_lacuna_declarada_e_o_scan_segue() -> None:
    zap = _ZapComAjax(ajax_falha=True)
    adapter = _adapter_com(zap)
    handle, estados = await _rodar(adapter, {"active": True, "ajax": True})

    # a recusa do add-on NÃO derruba o scan: ele degrada pro active e termina
    assert estados[-1] == ScanStatus.DONE
    assert "/JSON/ascan/action/scan/" in zap.chamadas

    bruto = await adapter.fetch_results(handle)
    assert any("AJAX spider" in g and "spiderAjax" in g for g in bruto.coverage_gaps), (
        f"a indisponibilidade do ajax tinha que virar lacuna; gaps={bruto.coverage_gaps}"
    )


async def test_sem_ajax_o_fluxo_antigo_spider_active_continua_intacto() -> None:
    zap = _ZapComAjax()
    adapter = _adapter_com(zap)
    _, estados = await _rodar(adapter, {"active": True})

    assert estados[-1] == ScanStatus.DONE
    assert "/JSON/ajaxSpider/action/scan/" not in zap.chamadas
    assert "/JSON/ascan/action/scan/" in zap.chamadas


def test_profile_ativo_liga_ajax_junto_com_o_active() -> None:
    from orchestrator.api.routers.scans import apply_profile

    out = apply_profile({}, "full")
    assert out["zap"]["active"] is True
    assert out["zap"]["ajax"] is True
    # o profile web (passivo) continua não ligando nenhum dos dois
    assert "zap" not in apply_profile({}, "web")
