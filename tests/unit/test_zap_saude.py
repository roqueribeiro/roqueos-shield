"""GOAL-SHIELD-01: o ZAP saudável e o 500 do accessUrl tratado.

Dois defeitos medidos na frota em 23/10/2026: `roqueos-pentest-zap (unhealthy)` nos
três ambientes, porque a imagem traz `ZAP_PORT=8080` e o HEALTHCHECK faz curl nessa
porta enquanto o daemon sobe na 8090; e `adapter.crashed` com traceback quando o ZAP
responde 500 no `accessUrl` de um alvo que ele não alcança.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from orchestrator.adapters.base import ScanIntegrityError
from orchestrator.adapters.zap_adapter import ZAPAdapter
from orchestrator.domain.schemas import AssetType, Target

_COMPOSE = Path(__file__).resolve().parents[2] / "docker" / "compose.scanners.yml"


def test_compose_dos_scanners_aponta_o_healthcheck_para_a_porta_do_daemon():
    zap = yaml.safe_load(_COMPOSE.read_text())["services"]["zap"]
    porta_do_daemon = zap["command"][zap["command"].index("-port") + 1]
    assert f"ZAP_PORT={porta_do_daemon}" in zap["environment"]


def _adapter(respostas: list[int]) -> tuple[ZAPAdapter, list[str]]:
    """ZAP falso: o accessUrl responde os códigos da lista, em ordem; o resto, 200."""
    chamadas: list[str] = []
    fila = list(respostas)

    def responder(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        if request.url.path == "/JSON/core/action/accessUrl/":
            codigo = fila.pop(0) if fila else 200
            return httpx.Response(codigo, json={"accessUrl": []})
        if request.url.path == "/JSON/spider/action/scan/":
            return httpx.Response(200, json={"scan": "1"})
        return httpx.Response(200, json={})

    adapter = ZAPAdapter(base_url="http://zap:8090", api_key="k")
    adapter._client = httpx.AsyncClient(
        base_url="http://zap:8090", transport=httpx.MockTransport(responder)
    )
    return adapter, chamadas


_ALVO = Target(asset_type=AssetType.URL, value="https://roqueos.com.br")


async def test_500_passageiro_no_access_url_ganha_segunda_chance_e_o_scan_comeca():
    adapter, chamadas = _adapter([500])
    handle = await adapter.start_scan(_ALVO, {})
    assert handle.metadata["spider_id"] == "1"
    assert chamadas.count("/JSON/core/action/accessUrl/") == 2


async def test_500_duas_vezes_vira_cobertura_incompleta_com_o_motivo():
    adapter, chamadas = _adapter([500, 500])
    with pytest.raises(ScanIntegrityError, match="zap não alcançou https://roqueos.com.br"):
        await adapter.start_scan(_ALVO, {})
    assert "/JSON/spider/action/scan/" not in chamadas


async def test_erro_do_cliente_no_access_url_nao_e_mascarado_como_alvo_fora_do_ar():
    adapter, chamadas = _adapter([400])
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.start_scan(_ALVO, {})
    assert chamadas.count("/JSON/core/action/accessUrl/") == 1


class _ZapFalso:
    """ZAP com estado: spider em 2 passos, fila passiva que esvazia, alertas paginados."""

    def __init__(self, alertas: list[dict], urls: int = 3, total_na_sessao: int | None = None):
        self.alertas = alertas
        self.urls = urls
        self.total_na_sessao = len(alertas) if total_na_sessao is None else total_na_sessao
        self.spider = iter(["50", "100"])
        self.fila = iter(["4", "0"])
        self.paginas: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        p, q = request.url.path, request.url.params
        if p == "/JSON/spider/action/scan/":
            return httpx.Response(200, json={"scan": "1"})
        if p == "/JSON/spider/view/status/":
            return httpx.Response(200, json={"status": next(self.spider)})
        if p == "/JSON/pscan/view/recordsToScan/":
            return httpx.Response(200, json={"recordsToScan": next(self.fila)})
        if p == "/JSON/core/view/urls/":
            return httpx.Response(200, json={"urls": [f"u{i}" for i in range(self.urls)]})
        if p == "/JSON/core/view/alerts/":
            inicio, quantos = int(q["start"]), int(q["count"])
            self.paginas.append((q["start"], q["count"]))
            return httpx.Response(200, json={"alerts": self.alertas[inicio : inicio + quantos]})
        if p == "/JSON/alert/view/alertCountsByRisk/":
            return httpx.Response(200, json={"High": str(self.total_na_sessao)})
        return httpx.Response(200, json={})


def _adapter_com(zap: _ZapFalso) -> ZAPAdapter:
    adapter = ZAPAdapter(base_url="http://zap:8090", api_key="k")
    adapter._client = httpx.AsyncClient(
        base_url="http://zap:8090", transport=httpx.MockTransport(zap)
    )
    return adapter


async def _rodar(adapter: ZAPAdapter):
    from orchestrator.domain.schemas import ScanStatus

    handle = await adapter.start_scan(_ALVO, {})
    estados = []
    for _ in range(6):
        estados.append(await adapter.poll(handle))
        if estados[-1] == ScanStatus.DONE:
            break
    return handle, [e.value for e in estados]


async def test_ciclo_completo_spider_fila_passiva_alertas_e_normalizacao():
    alerta = {
        "pluginId": "40012",
        "name": "XSS refletido",
        "risk": "High",
        "confidence": "Confirmed",
        "url": "https://roqueos.com.br/?q=1",
        "param": "q",
        "cweid": "79",
        "description": "d",
        "solution": "escape",
        "evidence": "<script>",
        "reference": "https://owasp.org/xss",
    }
    zap = _ZapFalso([alerta, {**alerta, "param": "sort", "cweid": "-1", "risk": "Esquisito"}])
    adapter = _adapter_com(zap)

    handle, estados = await _rodar(adapter)
    # spider 50% -> spider 100% (vai para a fila passiva) -> fila 4 -> fila 0
    assert estados == ["running", "running", "running", "done"]

    bruto = await adapter.fetch_results(handle)
    assert bruto.coverage_gaps == []
    achados = await adapter.normalize(bruto)
    assert [(f.title, f.severity.value, f.confidence.value, f.cwe) for f in achados] == [
        ("XSS refletido", "high", "certain", ["CWE-79"]),
        ("XSS refletido", "low", "certain", []),
    ]
    # mesmo plugin e mesma URL, parâmetros diferentes: dois achados, duas chaves
    assert len({f.dedup_discriminator for f in achados}) == 2
    assert achados[0].remediation == "escape"


async def test_alertas_paginados_ate_o_fim_e_redirecionamento_vira_lacuna_declarada():
    alertas = [
        {"name": f"a{i}", "risk": "Low", "url": "https://roqueos.com.br/x"} for i in range(501)
    ]
    zap = _ZapFalso(alertas, total_na_sessao=530)
    adapter = _adapter_com(zap)
    handle, _ = await _rodar(adapter)

    bruto = await adapter.fetch_results(handle)
    assert len(bruto.payload["alerts"]) == 501
    assert zap.paginas == [("0", "500"), ("500", "500")]
    assert len(bruto.coverage_gaps) == 1
    assert "530 alerta(s) na sessão mas só 501" in bruto.coverage_gaps[0]


async def test_spider_que_nao_rastreou_nada_nao_vira_alvo_limpo():
    adapter = _adapter_com(_ZapFalso([], urls=0))
    handle, estados = await _rodar(adapter)
    assert estados[-1] == "done"
    with pytest.raises(ScanIntegrityError, match="NENHUMA URL"):
        await adapter.fetch_results(handle)
