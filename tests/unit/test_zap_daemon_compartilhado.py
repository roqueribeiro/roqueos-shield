"""O daemon do ZAP é compartilhado entre scans: o que um scan deixa nele não pode valer
para o próximo. Dois defeitos achados pela régua do DAST em 20/11/2026:

1. ALERTA VELHO: o scan devolvia os alertas de scans anteriores do mesmo alvo (a sessão
   do daemon guarda tudo). Uma injeção de comando de uma versão anterior do alvo voltou
   no scan seguinte; quem corrige a falha e escaneia de novo continuava vendo a falha.
2. CREDENCIAL QUE VAZA: a regra do replacer com o header de autenticação valia para
   TODA requisição do daemon e nunca era removida. O Cookie/Authorization de um usuário
   ia junto nos scans seguintes de qualquer alvo.
"""

from __future__ import annotations

from typing import Any

import httpx

from orchestrator.adapters.zap_adapter import ZAPAdapter
from orchestrator.domain.schemas import AssetType, ScanStatus, Target


class _Zap:
    def __init__(
        self,
        *,
        delete_falha: bool = False,
        antigos: int = 0,
        por_vez: int = 7,
        site_desconhecido: bool = False,
        delete_site_falha: bool = False,
    ) -> None:
        self.delete_falha = delete_falha
        self.site_desconhecido = site_desconhecido
        self.delete_site_falha = delete_site_falha
        self.sites_esquecidos: list[str] = []
        # Como o ZAP 2.17 de verdade: cada deleteAlerts apaga só um pedaço.
        self.antigos = antigos
        self.por_vez = por_vez
        self.chamadas: list[tuple[str, dict[str, str]]] = []
        self.regras: dict[str, dict[str, str]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        p, q = request.url.path, dict(request.url.params)
        self.chamadas.append((p, q))
        if p == "/JSON/core/action/deleteSiteNode/":
            self.sites_esquecidos.append(q["url"])
            if self.site_desconhecido:
                return httpx.Response(400, json={"code": "does_not_exist"})
            if self.delete_site_falha:
                return httpx.Response(500, json={"code": "internal_error"})
            return httpx.Response(200, json={"Result": "OK"})
        if p == "/JSON/alert/view/numberOfAlerts/":
            if self.delete_falha:
                return httpx.Response(400, json={"code": "bad_action"})
            return httpx.Response(200, json={"numberOfAlerts": str(self.antigos)})
        if p == "/JSON/alert/action/deleteAlerts/":
            apagados = min(self.por_vez, self.antigos)
            self.antigos -= apagados
            return httpx.Response(200, json={"deleteAlerts": str(apagados)})
        if p == "/JSON/replacer/action/addRule/":
            self.regras[q["description"]] = q
            return httpx.Response(200, json={"Result": "OK"})
        if p == "/JSON/replacer/action/removeRule/":
            self.regras.pop(q["description"], None)
            return httpx.Response(200, json={"Result": "OK"})
        if p == "/JSON/spider/action/scan/":
            return httpx.Response(200, json={"scan": "1"})
        if p == "/JSON/spider/view/status/":
            return httpx.Response(200, json={"status": "100"})
        if p == "/JSON/pscan/view/recordsToScan/":
            return httpx.Response(200, json={"recordsToScan": "0"})
        if p == "/JSON/core/view/urls/":
            return httpx.Response(200, json={"urls": ["u1", "u2"]})
        if p == "/JSON/core/view/alerts/":
            return httpx.Response(200, json={"alerts": []})
        if p == "/JSON/alert/view/alertCountsByRisk/":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    def indice(self, caminho: str) -> int:
        return [c for c, _ in self.chamadas].index(caminho)


def _adapter(zap: _Zap) -> ZAPAdapter:
    a = ZAPAdapter(base_url="http://zap:8090", api_key="k")
    a._client = httpx.AsyncClient(base_url="http://zap:8090", transport=httpx.MockTransport(zap))
    return a


async def _ate_o_fim(a: ZAPAdapter, alvo: str, opcoes: dict[str, Any]):  # type: ignore[no-untyped-def]
    h = await a.start_scan(Target(asset_type=AssetType.URL, value=alvo), opcoes)
    for _ in range(6):
        if await a.poll(h) in (ScanStatus.DONE, ScanStatus.FAILED):
            break
    return h


async def test_scan_apaga_todos_os_alertas_anteriores_do_alvo_antes_do_spider() -> None:
    # Mutação: tirar o deleteAlerts -> os 65 alertas velhos continuam lá.
    zap = _Zap(antigos=65)
    a = _adapter(zap)
    h = await _ate_o_fim(a, "http://loja:8088/", {})
    assert zap.antigos == 0  # em várias chamadas, como o ZAP de verdade exige
    apagou = [q for c, q in zap.chamadas if c == "/JSON/alert/action/deleteAlerts/"]
    # Com e sem a barra final, porque o alerta de DOM XSS sai sem ela.
    assert {q["baseurl"] for q in apagou} == {"http://loja:8088/", "http://loja:8088"}
    assert zap.indice("/JSON/alert/action/deleteAlerts/") < zap.indice("/JSON/spider/action/scan/")
    raw = await a.fetch_results(h)
    assert not any("anteriores" in g for g in raw.coverage_gaps)


async def test_alerta_velho_que_nao_sai_vira_lacuna_com_o_numero() -> None:
    zap = _Zap(antigos=5, por_vez=0)  # o daemon não apaga nada
    a = _adapter(zap)
    h = await _ate_o_fim(a, "http://loja:8088/", {})
    raw = await a.fetch_results(h)
    assert any(g.startswith("5 alerta(s) de scans anteriores") for g in raw.coverage_gaps)


async def test_limpeza_que_falha_vira_lacuna_declarada() -> None:
    zap = _Zap(delete_falha=True)
    a = _adapter(zap)
    h = await _ate_o_fim(a, "http://loja:8088/", {})
    raw = await a.fetch_results(h)
    assert any("scans anteriores" in g for g in raw.coverage_gaps)


async def test_header_de_autenticacao_vale_so_para_a_origem_do_alvo() -> None:
    # Mutação: tirar o `url=` da regra -> ela vale para qualquer alvo do daemon.
    zap = _Zap()
    await _ate_o_fim(_adapter(zap), "https://app.cliente.com/login", {"headers": {"Cookie": "s=1"}})
    (regra,) = zap.regras.values()
    import re

    padrao = re.compile(regra["url"])
    assert padrao.match("https://app.cliente.com/api/conta")
    assert padrao.match("https://app.cliente.com")
    assert not padrao.match("https://outro-alvo.com/")
    assert not padrao.match("https://app.cliente.com.atacante.com/")


async def test_cleanup_tira_do_daemon_so_as_regras_deste_scan() -> None:
    # Mutação: cleanup que não remove -> a credencial fica no daemon para o próximo scan.
    zap = _Zap()
    a = _adapter(zap)
    h1 = await _ate_o_fim(a, "https://a.com/", {"headers": {"Authorization": "Bearer A"}})
    h2 = await _ate_o_fim(a, "https://b.com/", {"headers": {"Authorization": "Bearer B"}})
    assert len(zap.regras) == 2
    await a.cleanup(h1)
    (sobrou,) = zap.regras.values()
    assert sobrou["replacement"] == "Bearer B"  # o scan que ainda roda não perde a sua
    await a.cleanup(h2)
    assert zap.regras == {}


async def test_scan_esquece_o_site_do_alvo_antes_do_spider() -> None:
    # Sem isto, o spider do segundo scan do mesmo alvo dizia "No seeds available" e não
    # percorria nada. Mutação: tirar o deleteSiteNode -> nenhum site esquecido.
    zap = _Zap()
    await _ate_o_fim(_adapter(zap), "http://loja:8088/produtos", {})
    assert zap.sites_esquecidos == ["http://loja:8088"]  # a origem, não a página
    assert zap.indice("/JSON/core/action/deleteSiteNode/") < zap.indice("/JSON/spider/action/scan/")


async def test_primeiro_scan_do_alvo_nao_e_lacuna() -> None:
    # O daemon nunca viu o site: `does_not_exist` é o caso normal, não um erro.
    zap = _Zap(site_desconhecido=True)
    a = _adapter(zap)
    raw = await a.fetch_results(await _ate_o_fim(a, "http://novo:8080/", {}))
    assert not any("scan anterior" in g for g in raw.coverage_gaps)


async def test_falha_ao_esquecer_o_site_vira_lacuna() -> None:
    zap = _Zap(delete_site_falha=True)
    a = _adapter(zap)
    raw = await a.fetch_results(await _ate_o_fim(a, "http://loja:8088/", {}))
    assert any("scan anterior deste alvo" in g for g in raw.coverage_gaps)
