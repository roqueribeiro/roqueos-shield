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


# --- Teto de recurso do AJAX spider + tolerância do poll (regressão de OOM ao vivo) ---
#
# No primeiro scan real contra o Juice Shop o ZAP morreu por OOM (exit 137) no meio do
# AJAX spider: o default é um browser headless por core (8+ Firefox no Mac) e juntos
# estouram a RAM da VM do Docker. O container morto parou de resolver no DNS, e o poll
# recebia "Name or service not known" a cada 5s. Dois consertos, um teste cada:
#
#   A. _start_ajax limita o nº de browsers ANTES de iniciar o crawl (não estoura a RAM);
#   B. o poll TOLERA alguns erros de transporte (timeout/DNS) e só reprova se persistir,
#      em vez de declarar "falhou" no primeiro soluço do daemon sob carga.


async def test_ajax_limita_browsers_antes_de_iniciar_o_crawl() -> None:
    """O teto de browsers é setado ANTES do scan do ajax (senão o ZAP OOMa na SPA)."""
    zap = _ZapComAjax()
    adapter = _adapter_com(zap)
    await _rodar(adapter, {"active": False, "ajax": True})

    assert "/JSON/ajaxSpider/action/setOptionNumberOfBrowsers/" in zap.chamadas, (
        "o nº de browsers tem que ser limitado antes do crawl, senão o ZAP morre por OOM"
    )
    assert zap.chamadas.index(
        "/JSON/ajaxSpider/action/setOptionNumberOfBrowsers/"
    ) < zap.chamadas.index("/JSON/ajaxSpider/action/scan/"), (
        "o teto tem que ser aplicado ANTES de iniciar o ajax, não depois"
    )


async def test_opcao_do_ajax_que_falha_nao_derruba_o_scan() -> None:
    """Add-on antigo que não conhece a opção vira aviso; o crawl roda mesmo assim."""

    class _ZapSemOpcao(_ZapComAjax):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            if "setOption" in request.url.path:
                self.chamadas.append(request.url.path)
                return httpx.Response(400, json={})  # opção desconhecida
            return super().__call__(request)

    zap = _ZapSemOpcao()
    adapter = _adapter_com(zap)
    _, estados = await _rodar(adapter, {"active": True, "ajax": True})

    assert estados[-1] == ScanStatus.DONE, "a opção recusada não pode derrubar o scan"
    assert "/JSON/ajaxSpider/action/scan/" in zap.chamadas, "o crawl tinha que rodar"


class _ZapAjaxQueTrava:
    """ZAP que entra no ajax e aí o daemon some (DNS/timeout) em toda consulta de status.

    Reproduz o container de ZAP morto por OOM: as chamadas de status viram erro de
    transporte. O poll tem que TOLERAR vários antes de desistir.
    """

    def __init__(self) -> None:
        self.status_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/JSON/spider/action/scan/":
            return httpx.Response(200, json={"scan": "1"})
        if p == "/JSON/spider/view/status/":
            return httpx.Response(200, json={"status": "100"})
        if p == "/JSON/ajaxSpider/action/scan/":
            return httpx.Response(200, json={"scan": "OK"})
        if p == "/JSON/ajaxSpider/view/status/":
            # o daemon morreu: resolução de nome falha, como no OOM real.
            self.status_calls += 1
            raise httpx.ConnectError("[Errno -2] Name or service not known")
        return httpx.Response(200, json={})


async def test_poll_tolera_erros_transientes_e_so_falha_depois_de_persistir() -> None:
    zap = _ZapAjaxQueTrava()
    adapter = _adapter_com(zap)
    handle = await adapter.start_scan(_ALVO, {"active": True, "ajax": True})

    estados: list[ScanStatus] = []
    for _ in range(20):
        estados.append(await adapter.poll(handle))
        if estados[-1] == ScanStatus.FAILED:
            break

    assert estados[-1] == ScanStatus.FAILED, "um daemon que não volta tem que acabar em FAILED"
    # a 1ª consulta de status do ajax falha e, se o poll não tolerasse, FAILED viria já na
    # 2ª chamada de poll (a 1ª transiciona spider->ajax). Exigir muitos RUNNING tolerados
    # antes do FAILED é o que mata o mutante "return FAILED no primeiro erro".
    primeiro_failed = estados.index(ScanStatus.FAILED)
    assert primeiro_failed >= 12, (
        f"o poll tinha que tolerar >=12 soluços antes de desistir; falhou no {primeiro_failed}"
    )
    assert estados[:primeiro_failed] == [ScanStatus.RUNNING] * primeiro_failed, (
        "enquanto tolera, o poll reporta RUNNING, nunca FAILED antecipado"
    )


# --- Retry do active scan no quirk "0" (regressão do scan real que morreu no ascan) ---
#
# No scan ao vivo do Juice Shop, o AJAX spider terminou e, ao disparar o active scan, o
# ZAP devolveu scan="0" (o mesmo quirk que o spider já trata): o browser headless ainda
# liberava memória e o daemon recusou o ascan por um instante. Sem retry, o scan morria
# com ascan_id_invalid num alvo que seria varrido 5s depois. O spider tinha retry; o
# ascan não tinha. Agora tem.


class _ZapAscanZeroUmaVez(_ZapComAjax):
    """O ascan/action/scan devolve '0' na 1ª vez (quirk sob carga) e aceita na 2ª."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self._ascan_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/JSON/ascan/action/scan/":
            self.chamadas.append(request.url.path)
            self._ascan_calls += 1
            return httpx.Response(200, json={"scan": "0" if self._ascan_calls == 1 else "2"})
        return super().__call__(request)


async def test_ascan_retenta_quando_zap_devolve_scan_id_zero() -> None:
    zap = _ZapAscanZeroUmaVez()
    adapter = _adapter_com(zap)
    _, estados = await _rodar(adapter, {"active": True, "ajax": True})

    assert estados[-1] == ScanStatus.DONE, "o '0' transitório não pode derrubar o active scan"
    assert zap.chamadas.count("/JSON/ascan/action/scan/") == 2, "tinha que retentar o ascan"
    # entre as duas tentativas, re-acessa o alvo pra resetar o estado interno do ZAP
    assert "/JSON/core/action/accessUrl/" in zap.chamadas


async def test_ascan_zero_nas_duas_tentativas_falha_honesto() -> None:
    """Duas recusas seguidas é FAILED de verdade (vetor não verificado), nunca 'limpo'."""

    class _ZapAscanSempreZero(_ZapComAjax):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/JSON/ascan/action/scan/":
                self.chamadas.append(request.url.path)
                return httpx.Response(200, json={"scan": "0"})
            return super().__call__(request)

    zap = _ZapAscanSempreZero()
    adapter = _adapter_com(zap)
    _, estados = await _rodar(adapter, {"active": True, "ajax": True})
    assert estados[-1] == ScanStatus.FAILED
    assert zap.chamadas.count("/JSON/ascan/action/scan/") == 2, "duas tentativas, aí desiste"


# --- Contador do poll como STREAK (zera num poll que responde), não soma do scan ----
#
# O poll tolera soluços de transporte (timeout sob carga, DNS do Docker oscilando sob
# pressão de memória). O teto é de CONSECUTIVOS: um poll que volta a responder zera a
# contagem. Sem o reset, soluços esparsos ao longo de um scan longo somavam 12 e
# derrubavam um scan sadio. Este teste intercala rajadas de soluço com respostas.


class _ZapAjaxBlips:
    """ZAP cujo status do ajax segue um padrão de 'raise'/'running'/'stopped'."""

    def __init__(self, padrao: list[str]) -> None:
        self._padrao = iter(padrao)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p == "/JSON/spider/action/scan/":
            return httpx.Response(200, json={"scan": "1"})
        if p == "/JSON/spider/view/status/":
            return httpx.Response(200, json={"status": "100"})
        if p == "/JSON/ajaxSpider/view/status/":
            nxt = next(self._padrao, "stopped")
            if nxt == "raise":
                raise httpx.ConnectError("[Errno -3] Temporary failure in name resolution")
            return httpx.Response(200, json={"status": nxt})
        if p == "/JSON/pscan/view/recordsToScan/":
            return httpx.Response(200, json={"recordsToScan": "0"})
        if p == "/JSON/core/view/urls/":
            return httpx.Response(200, json={"urls": ["u0", "u1", "u2"]})
        return httpx.Response(200, json={})


async def test_solucos_esparsos_nao_derrubam_um_scan_sadio() -> None:
    # duas rajadas de 8 soluços separadas por uma resposta: 16 erros no total, mas nunca
    # 12 SEGUIDOS. Com o reset, o scan termina; sem o reset, o total cruza 12 e falha.
    padrao = ["raise"] * 8 + ["running"] + ["raise"] * 8 + ["stopped"]
    zap = _ZapAjaxBlips(padrao)
    adapter = _adapter_com(zap)

    handle = await adapter.start_scan(_ALVO, {"active": False, "ajax": True})
    estados: list[ScanStatus] = []
    for _ in range(30):
        estados.append(await adapter.poll(handle))
        if estados[-1] in (ScanStatus.DONE, ScanStatus.FAILED):
            break

    assert estados[-1] == ScanStatus.DONE, (
        f"soluços intercalados com respostas não podem somar até o teto; estados={estados}"
    )


# --- Teto de recurso do active scan (pra caber numa VM pequena sem desligar vetor) ---
#
# Ao entrar no active scan a sessão do ZAP já carrega o que o ajax descobriu; o ascan
# injeta por regra/parâmetro/URL e o volume estourava a memória do container em ~1min.
# A escolha do founder foi "limitar pra caber": menos threads concorrentes + teto de
# tempo, com TODAS as regras ligadas. Estes limites são setados ANTES de iniciar o ascan.


async def test_ascan_limita_recursos_antes_de_iniciar() -> None:
    zap = _ZapComAjax()
    adapter = _adapter_com(zap)
    _, estados = await _rodar(adapter, {"active": True, "ajax": True})

    assert estados[-1] == ScanStatus.DONE
    assert "/JSON/ascan/action/setOptionThreadPerHost/" in zap.chamadas, (
        "a concorrência do active scan tem que ser limitada, senão estoura a memória"
    )
    assert zap.chamadas.index("/JSON/ascan/action/setOptionThreadPerHost/") < zap.chamadas.index(
        "/JSON/ascan/action/scan/"
    ), "o teto tem que ser aplicado ANTES de iniciar o active scan"


async def test_opcao_do_ascan_que_falha_nao_derruba_o_scan() -> None:
    """Add-on antigo que não conhece a opção de ascan vira aviso; o scan roda mesmo assim."""

    class _ZapSemOpcaoAscan(_ZapComAjax):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            if request.url.path.startswith("/JSON/ascan/action/setOption"):
                self.chamadas.append(request.url.path)
                return httpx.Response(400, json={})
            return super().__call__(request)

    zap = _ZapSemOpcaoAscan()
    adapter = _adapter_com(zap)
    _, estados = await _rodar(adapter, {"active": True, "ajax": True})
    assert estados[-1] == ScanStatus.DONE, "opção de ascan recusada não pode derrubar o scan"
    assert "/JSON/ascan/action/scan/" in zap.chamadas, "o active scan tinha que rodar"
