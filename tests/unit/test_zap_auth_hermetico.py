"""Scan autenticado no ZAP: a credencial não vaza para outro alvo, nem sobra no daemon.

O daemon ZAP é um só e o worker roda até `max_jobs` scans em paralelo contra ele. A
versão anterior punha o cabeçalho de auth numa regra GLOBAL de replacer e nunca a
tirava: o cookie do alvo A seguia em todo request dos scans seguintes, de qualquer
alvo. E o spider, seguindo o link de "sair", derrubava a sessão no meio e o resto do
scan rodava sem login com cara de cobertura completa.

Estes testes provam:

1. a regra de auth tem escopo de URL (só a origem do alvo) e sai no `cleanup`;
2. a regra de um scan vizinho VIVO não é tocada; a de scan morto (velha ou no formato
   antigo) e a do mesmo alvo saem antes do scan começar;
3. se o resto não sai, ou a lista não pode ser lida, o scan não começa (falha fechado);
4. com auth, o logout fica fora num contexto só do scan, usado por spider e ascan;
5. exclusão recusada falha fechado, e o que o scan já tinha criado é desfeito;
6. replacer recusado vira lacuna declarada ("SEM login"), nunca autenticado calado;
7. falha no meio do `start_scan` também desfaz a regra.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
import pytest

from orchestrator.adapters.base import ScanIntegrityError
from orchestrator.adapters.zap_adapter import _LOGOUT, _REGRA_AUTH, ZAPAdapter
from orchestrator.domain.schemas import AssetType, ScanStatus, Target

_ALVO = Target(asset_type=AssetType.URL, value="http://cai-dvwa:80/vulnerabilities/sqli/")
_COOKIE = {"Cookie": "PHPSESSID=segredo; security=low"}


class _ZapComEstado:
    """ZAP falso que guarda regras de replacer e contextos como o daemon real."""

    def __init__(self, *, regras: list[dict[str, str]] | None = None) -> None:
        self.regras: list[dict[str, str]] = list(regras or [])
        self.contextos: dict[str, dict[str, Any]] = {}
        self.chamadas: list[tuple[str, dict[str, str]]] = []
        self.falhar: dict[str, int] = {}  # path -> status http forçado

    def __call__(self, request: httpx.Request) -> httpx.Response:
        p, q = request.url.path, dict(request.url.params)
        self.chamadas.append((p, q))
        if p in self.falhar:
            return httpx.Response(self.falhar[p], json={"code": "forced"})
        if p == "/JSON/replacer/view/rules/":
            return httpx.Response(200, json={"rules": self.regras})
        if p == "/JSON/replacer/action/addRule/":
            self.regras.append({"description": q["description"], "url": q.get("url", "")})
            return httpx.Response(200, json={"Result": "OK"})
        if p == "/JSON/replacer/action/removeRule/":
            self.regras = [r for r in self.regras if r["description"] != q["description"]]
            return httpx.Response(200, json={"Result": "OK"})
        if p == "/JSON/context/view/contextList/":
            return httpx.Response(
                200, json={"contextList": str(["Default Context", *self.contextos])}
            )
        if p == "/JSON/context/action/newContext/":
            self.contextos[q["contextName"]] = {"id": str(len(self.contextos) + 1), "ex": []}
            return httpx.Response(200, json={"contextId": self.contextos[q["contextName"]]["id"]})
        if p == "/JSON/context/action/includeInContext/":
            self.contextos[q["contextName"]]["in"] = q["regex"]
            return httpx.Response(200, json={"Result": "OK"})
        if p == "/JSON/context/action/excludeFromContext/":
            self.contextos[q["contextName"]]["ex"].append(q["regex"])
            return httpx.Response(200, json={"Result": "OK"})
        if p == "/JSON/context/action/removeContext/":
            self.contextos.pop(q["contextName"], None)
            return httpx.Response(200, json={"Result": "OK"})
        if p == "/JSON/spider/action/scan/":
            return httpx.Response(200, json={"scan": "1"})
        if p == "/JSON/spider/view/status/":
            return httpx.Response(200, json={"status": "100"})
        if p == "/JSON/ascan/action/scan/":
            return httpx.Response(200, json={"scan": "2"})
        if p == "/JSON/ascan/view/status/":
            return httpx.Response(200, json={"status": "100"})
        if p == "/JSON/pscan/view/recordsToScan/":
            return httpx.Response(200, json={"recordsToScan": "0"})
        if p == "/JSON/core/view/urls/":
            return httpx.Response(200, json={"urls": ["u1", "u2"]})
        if p == "/JSON/core/view/alerts/":
            return httpx.Response(200, json={"alerts": []})
        return httpx.Response(200, json={})

    def chamou(self, path: str) -> list[dict[str, str]]:
        return [q for p, q in self.chamadas if p == path]


def _adapter(zap: _ZapComEstado) -> ZAPAdapter:
    a = ZAPAdapter(base_url="http://zap:8090", api_key="k")
    a._client = httpx.AsyncClient(base_url="http://zap:8090", transport=httpx.MockTransport(zap))
    return a


async def _ate_o_fim(adapter: ZAPAdapter, handle) -> None:
    for _ in range(10):
        if await adapter.poll(handle) in (ScanStatus.DONE, ScanStatus.FAILED):
            return


def _regra(descricao: str, url: str = "(?i)^http://outro:80$") -> dict[str, str]:
    return {"description": descricao, "url": url}


# --- 1. escopo + cleanup ---------------------------------------------------------


async def test_regra_de_auth_tem_escopo_do_alvo_e_sai_no_cleanup() -> None:
    zap = _ZapComEstado()
    adapter = _adapter(zap)
    handle = await adapter.start_scan(_ALVO, {"active": True, "headers": _COOKIE})

    [criada] = zap.chamou("/JSON/replacer/action/addRule/")
    assert criada["matchString"] == "Cookie"
    escopo = re.compile(criada["url"])
    assert escopo.match("http://cai-dvwa/vulnerabilities/sqli/?id=1")
    assert escopo.match("http://cai-dvwa:80/login.php")
    assert not escopo.match("http://outro-alvo/"), "cookie do DVWA iria pra outro alvo"
    assert not escopo.match("http://cai-dvwa.atacante.com/")
    assert handle.metadata["autenticado"] is True

    await _ate_o_fim(adapter, handle)
    await adapter.cleanup(handle)
    assert zap.regras == [], f"a credencial ficou no daemon: {zap.regras}"


async def test_o_valor_do_cabecalho_nunca_vai_pro_metadata() -> None:
    zap = _ZapComEstado()
    handle = await _adapter(zap).start_scan(_ALVO, {"headers": _COOKIE})
    assert "segredo" not in repr(handle.metadata)


# --- 2. restos ---------------------------------------------------------------------


async def test_regra_de_scan_vizinho_vivo_nao_e_tocada() -> None:
    viva = _regra(f"{_REGRA_AUTH}{int(time.time())}-abcd1234-Authorization")
    zap = _ZapComEstado(regras=[viva])
    await _adapter(zap).start_scan(_ALVO, {"headers": _COOKIE})
    assert viva in zap.regras, "derrubou a sessão de um scan que estava rodando"


async def test_resto_de_scan_morto_sai_antes_de_comecar() -> None:
    velha = _regra(f"{_REGRA_AUTH}{int(time.time()) - 3 * 3600}-abcd1234-Cookie")
    formato_antigo = _regra(f"{_REGRA_AUTH}Cookie")  # o que a versão anterior deixava
    alheia = _regra("regra do operador", "")
    zap = _ZapComEstado(regras=[velha, formato_antigo, alheia])
    await _adapter(zap).start_scan(_ALVO, {})
    assert velha not in zap.regras and formato_antigo not in zap.regras
    assert alheia in zap.regras, "regra que não é nossa não se apaga"


async def test_regra_do_mesmo_alvo_sai_mesmo_recente() -> None:
    escopo = ZAPAdapter._escopo(_ALVO.value)
    mesma = _regra(f"{_REGRA_AUTH}{int(time.time())}-abcd1234-Cookie", escopo)
    zap = _ZapComEstado(regras=[mesma])
    await _adapter(zap).start_scan(_ALVO, {})
    assert mesma not in zap.regras, "scan sem auth herdaria o login de outro scan"


# --- 3. falha fechado ------------------------------------------------------------


async def test_resto_que_nao_sai_impede_o_scan() -> None:
    velha = _regra(f"{_REGRA_AUTH}Cookie")
    zap = _ZapComEstado(regras=[velha])
    zap.falhar["/JSON/replacer/action/removeRule/"] = 500
    with pytest.raises(ScanIntegrityError, match="não saiu"):
        await _adapter(zap).start_scan(_ALVO, {"headers": _COOKIE})
    assert not zap.chamou("/JSON/replacer/action/addRule/")
    assert not zap.chamou("/JSON/spider/action/scan/")


async def test_lista_de_regras_ilegivel_impede_o_scan() -> None:
    zap = _ZapComEstado()
    zap.falhar["/JSON/replacer/view/rules/"] = 500
    with pytest.raises(ScanIntegrityError, match="regras de autenticação"):
        await _adapter(zap).start_scan(_ALVO, {})


async def test_sem_add_on_replacer_o_scan_sem_auth_segue() -> None:
    zap = _ZapComEstado()
    zap.falhar["/JSON/replacer/view/rules/"] = 404
    handle = await _adapter(zap).start_scan(_ALVO, {})
    assert handle.native_id


# --- 4. logout fora, num contexto só do scan -------------------------------------


async def test_scan_autenticado_exclui_logout_no_contexto_do_scan() -> None:
    zap = _ZapComEstado()
    adapter = _adapter(zap)
    handle = await adapter.start_scan(_ALVO, {"active": True, "headers": _COOKIE})

    [ctx] = list(zap.contextos)
    assert ctx.startswith("cai-ctx-")
    assert _LOGOUT in zap.contextos[ctx]["ex"]
    assert zap.contextos[ctx]["in"] == ZAPAdapter._escopo(_ALVO.value)
    [spider] = zap.chamou("/JSON/spider/action/scan/")
    assert spider["contextName"] == ctx

    await _ate_o_fim(adapter, handle)
    [ascan] = zap.chamou("/JSON/ascan/action/scan/")
    assert ascan["contextId"] == zap.contextos[ctx]["id"]
    assert not zap.chamou("/JSON/spider/action/excludeFromScan/"), "lista global vaza"

    await adapter.cleanup(handle)
    assert zap.contextos == {}


async def test_exclusao_pedida_entra_mesmo_sem_auth() -> None:
    zap = _ZapComEstado()
    await _adapter(zap).start_scan(_ALVO, {"exclude": [r".*/apagar-conta.*"]})
    [ctx] = list(zap.contextos)
    assert zap.contextos[ctx]["ex"] == [r".*/apagar-conta.*"]


async def test_sem_auth_e_sem_exclusao_o_fluxo_antigo_fica_igual() -> None:
    zap = _ZapComEstado()
    await _adapter(zap).start_scan(_ALVO, {})
    assert zap.contextos == {}
    [spider] = zap.chamou("/JSON/spider/action/scan/")
    assert "contextName" not in spider


@pytest.mark.parametrize(
    "url",
    [
        "http://cai-dvwa/logout.php",
        "http://x/Logout",
        "http://x/account/sign-out",
        "http://x/auth/signoff",
        "http://x/sair",
        "http://x/encerrar-sessao",
    ],
)
def test_logout_casa_os_jeitos_comuns(url: str) -> None:
    assert re.match(_LOGOUT, url)


@pytest.mark.parametrize(
    "url", ["http://x/login.php", "http://x/vulnerabilities/sqli/", "http://x/sairda"]
)
def test_logout_nao_esconde_o_resto(url: str) -> None:
    assert not re.match(_LOGOUT, url)


# --- 5. exclusão recusada --------------------------------------------------------


async def test_exclusao_recusada_falha_fechado_e_desfaz() -> None:
    zap = _ZapComEstado()
    zap.falhar["/JSON/context/action/excludeFromContext/"] = 500
    with pytest.raises(ScanIntegrityError, match="exclusões"):
        await _adapter(zap).start_scan(_ALVO, {"headers": _COOKIE})
    assert zap.regras == [], "a regra criada antes da falha ficou no daemon"
    assert zap.contextos == {}
    assert not zap.chamou("/JSON/spider/action/scan/")


# --- 6. replacer recusado é lacuna -----------------------------------------------


async def test_replacer_recusado_vira_lacuna_declarada() -> None:
    zap = _ZapComEstado()
    zap.falhar["/JSON/replacer/action/addRule/"] = 400
    adapter = _adapter(zap)
    handle = await adapter.start_scan(_ALVO, {"headers": _COOKIE})
    assert handle.metadata["autenticado"] is False
    await _ate_o_fim(adapter, handle)
    raw = await adapter.fetch_results(handle)
    assert any("SEM login" in g for g in raw.coverage_gaps), raw.coverage_gaps


async def test_openapi_que_nao_importa_vira_lacuna() -> None:
    zap = _ZapComEstado()
    zap.falhar["/JSON/openapi/action/importUrl/"] = 500
    adapter = _adapter(zap)
    handle = await adapter.start_scan(_ALVO, {"openapi_url": "http://cai-dvwa/openapi.json"})
    await _ate_o_fim(adapter, handle)
    raw = await adapter.fetch_results(handle)
    assert any("OpenAPI" in g for g in raw.coverage_gaps), raw.coverage_gaps


# --- 7. falha no meio desfaz ------------------------------------------------------


async def test_alvo_inalcancavel_depois_da_regra_nao_deixa_credencial() -> None:
    zap = _ZapComEstado()
    zap.falhar["/JSON/core/action/accessUrl/"] = 500
    with pytest.raises(ScanIntegrityError):
        await _adapter(zap).start_scan(_ALVO, {"headers": _COOKIE})
    assert zap.regras == [] and zap.contextos == {}
