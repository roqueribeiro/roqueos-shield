"""Issue #10: o dashboard antigo em /ui sob CSP estrito, sem CDN e sem token no navegador.

Antes: Tailwind play-cdn (exige 'unsafe-eval'), Alpine e Chart.js de CDN sem SRI, o
token da API em localStorage (e em ?token= na URL do cockpit e do relatório), e o /ui
isento de CSP no main.py. Cada teste aqui reprova se um desses voltar.
"""

from __future__ import annotations

import base64
import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from orchestrator import main

STATIC = Path(main.__file__).parent / "static"
PAGINAS = sorted(STATIC.glob("*.html"))
APP_JS = STATIC / "app.js"


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.dentro_de_script: list[str] = []
        self._em_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        self._em_script = tag == "script"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._em_script = False

    def handle_data(self, data: str) -> None:
        if self._em_script and data.strip():
            self.dentro_de_script.append(data.strip())


def _tags(pagina: Path) -> _Tags:
    p = _Tags()
    p.feed(pagina.read_text(encoding="utf-8"))
    return p


def test_ha_paginas_para_conferir() -> None:
    # Sem isto, um glob vazio deixaria todos os testes abaixo verdes sem olhar nada.
    assert {p.name for p in PAGINAS} >= {"index.html", "cockpit.html"}


# ---------------------------------------------------------------- CSP no /ui


def test_csp_do_ui_e_estrito() -> None:
    csp = main._csp_para("/ui/")
    assert csp is not None
    diretivas = {d.split()[0]: d.split()[1:] for d in csp.split("; ")}
    assert diretivas["script-src"] == ["'self'"]
    assert diretivas["style-src"] == ["'self'"]
    assert diretivas["default-src"] == ["'none'"]
    assert diretivas["frame-ancestors"] == ["'none'"]
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert "http" not in csp


@pytest.mark.parametrize(
    "caminho", ["/ui", "/ui/", "/ui/index.html", "/ui/cockpit.html", "/ui/app.js"]
)
def test_ui_nao_esta_isento(caminho: str) -> None:
    assert main._csp_para(caminho) == main._CSP_UI


def test_isencoes_sao_so_docs_e_redoc() -> None:
    assert main._SEM_CSP == ("/docs", "/redoc")
    assert main._csp_para("/docs") is None
    assert main._csp_para("/health") == main._CSP
    # /uix não é o /ui: prefixo sem a barra não pode pegar a CSP do dashboard por engano.
    assert main._csp_para("/uix") == main._CSP


def _app_com_middleware() -> Starlette:
    # O middleware real em volta dos arquivos reais: vale com ou sem o build da tela
    # nova (com o build, o main.py redireciona o /ui e o mount do static nem existe).
    async def docs(_: object) -> PlainTextResponse:
        return PlainTextResponse("docs")

    app = Starlette(
        routes=[
            Route("/docs", docs),
            Mount("/ui", StaticFiles(directory=str(STATIC), html=True)),
        ]
    )
    return main.CabecalhosDeSeguranca(app)  # type: ignore[return-value]


@pytest.mark.parametrize("caminho", ["/ui/", "/ui/cockpit.html", "/ui/app.js", "/ui/styles.css"])
async def test_resposta_do_ui_leva_a_csp(caminho: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_app_com_middleware()), base_url="http://t"
    ) as c:
        r = await c.get(caminho)
        assert r.status_code == 200
        assert r.headers["content-security-policy"] == main._CSP_UI
        assert r.headers["x-frame-options"] == "DENY"
        docs = await c.get("/docs")
        assert "content-security-policy" not in docs.headers


# ---------------------------------------------------------------- sem CDN, sem inline


@pytest.mark.parametrize("pagina", PAGINAS, ids=lambda p: p.name)
def test_html_nao_referencia_endereco_externo(pagina: Path) -> None:
    for tag, attrs in _tags(pagina).tags:
        for nome in ("src", "href"):
            valor = attrs.get(nome) or ""
            assert not re.match(r"^(https?:)?//", valor, re.I), (
                f"{pagina.name}: <{tag} {nome}={valor}>"
            )
    texto = pagina.read_text(encoding="utf-8")
    for cdn in ("cdn.tailwindcss.com", "cdn.jsdelivr.net", "unpkg.com", "cdnjs"):
        assert cdn not in texto, f"{pagina.name} ainda cita {cdn}"


@pytest.mark.parametrize("pagina", PAGINAS, ids=lambda p: p.name)
def test_html_sem_script_nem_estilo_inline(pagina: Path) -> None:
    t = _tags(pagina)
    assert not t.dentro_de_script, f"{pagina.name}: script inline {t.dentro_de_script[0][:60]!r}"
    for tag, attrs in t.tags:
        if tag == "script":
            assert attrs.get("src"), f"{pagina.name}: <script> sem src"
        if tag == "style":
            pytest.fail(f"{pagina.name}: <style> inline")
        for nome in attrs:
            assert nome != "style", f"{pagina.name}: style= em <{tag}>"
            assert not nome.startswith("on"), f"{pagina.name}: handler inline {nome} em <{tag}>"


def _sri(arquivo: Path) -> str:
    return "sha384-" + base64.b64encode(hashlib.sha384(arquivo.read_bytes()).digest()).decode()


@pytest.mark.parametrize("pagina", PAGINAS, ids=lambda p: p.name)
def test_libs_e_css_com_sri_que_bate(pagina: Path) -> None:
    vistos = 0
    for tag, attrs in _tags(pagina).tags:
        ref = attrs.get("src") if tag == "script" else attrs.get("href") if tag == "link" else None
        if not ref or not (ref.startswith("vendor/") or ref == "styles.css"):
            continue
        vistos += 1
        arquivo = STATIC / ref
        assert arquivo.is_file(), f"{pagina.name}: {ref} não existe"
        assert attrs.get("integrity") == _sri(arquivo), f"{pagina.name}: SRI de {ref} não bate"
    assert vistos >= 2


def test_cada_lib_vendorizada_tem_licenca() -> None:
    vendor = STATIC / "vendor"
    libs = {p.name for p in vendor.glob("*.js")}
    assert libs == {"alpinejs-csp-3.17.5.min.js", "chart-4.4.0.umd.min.js"}
    licencas = {p.name for p in vendor.glob("LICENSE*")}
    for lic in (
        "LICENSE.alpinejs.md",
        "LICENSE.chartjs.md",
        "LICENSE.tailwindcss",
        "LICENSE.vue-reactivity",
    ):
        assert lic in licencas
        assert "MIT" in (vendor / lic).read_text(encoding="utf-8")
    assert (
        "Chart.js v4.4.0" in (vendor / "chart-4.4.0.umd.min.js").read_text(encoding="utf-8")[:200]
    )


def test_nenhum_build_do_alpine_que_precisa_de_eval() -> None:
    # O build normal do Alpine usa new Function: sob script-src 'self' ele não roda.
    for pagina in PAGINAS:
        for tag, attrs in _tags(pagina).tags:
            if tag == "script" and "alpine" in (attrs.get("src") or ""):
                assert "alpinejs-csp" in (attrs.get("src") or "")
    for js in (STATIC / "vendor").glob("*.js"):
        texto = js.read_text(encoding="utf-8")
        assert "new Function" not in texto, js.name
        assert not re.search(r"\beval\(", texto), js.name


_EXPRESSAO_ALPINE = re.compile(r"^(x-[\w.:-]+|:[\w.-]+|@[\w.:-]+)$")


@pytest.mark.parametrize("pagina", PAGINAS, ids=lambda p: p.name)
def test_expressoes_alpine_cabem_no_build_csp(pagina: Path) -> None:
    # O parser do build CSP não entende template string, arrow, `?.` nem `??`: a
    # expressão quebra só no navegador, em silêncio para o servidor.
    for tag, attrs in _tags(pagina).tags:
        for nome, valor in attrs.items():
            if not _EXPRESSAO_ALPINE.match(nome) or not valor:
                continue
            for proibido in ("`", "=>", "?.", "??"):
                assert proibido not in valor, f"{pagina.name}: <{tag} {nome}={valor!r}>"
            if nome == "x-data":
                assert re.fullmatch(r"\w+", valor), f"{pagina.name}: x-data={valor!r}"


def test_classes_estaticas_existem_no_css_gerado() -> None:
    # styles.css é gerado (tailwind/); classe nova no HTML sem regenerar some na tela.
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    sem_regra = {"dark"}
    faltando = []
    for pagina in PAGINAS:
        for _tag, attrs in _tags(pagina).tags:
            for classe in (attrs.get("class") or "").split():
                if classe in sem_regra:
                    continue
                escapada = re.sub(r"([:/.\[\]%#])", r"\\\1", classe)
                if "." + escapada not in css:
                    faltando.append(f"{pagina.name}: {classe}")
    assert not faltando, faltando


# ---------------------------------------------------------------- auth por cookie


def _codigo(js: str) -> str:
    # Tira comentários, para a explicação no cabeçalho não contar como uso.
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", js)


def test_app_js_nao_guarda_token_no_navegador() -> None:
    codigo = _codigo(APP_JS.read_text(encoding="utf-8"))
    assert "localStorage" not in codigo
    assert "sessionStorage" not in codigo
    assert "indexedDB" not in codigo
    assert "document.cookie" not in codigo


def test_app_js_nao_manda_token_nem_em_cabecalho_nem_na_url() -> None:
    codigo = _codigo(APP_JS.read_text(encoding="utf-8"))
    assert "X-API-Token" not in codigo
    assert not re.search(r"[?&]token=", codigo)
    for pagina in PAGINAS:
        assert not re.search(r"[?&]token=", pagina.read_text(encoding="utf-8")), pagina.name


def test_app_js_usa_o_cookie_de_sessao_e_o_login_existente() -> None:
    codigo = _codigo(APP_JS.read_text(encoding="utf-8"))
    assert "credentials: 'same-origin'" in codigo
    assert "'/auth/session'" in codigo
    # Escrita por cookie exige o cabeçalho anti-CSRF que o deps.py confere.
    from orchestrator.api.deps import CABECALHO_CSRF

    assert f"const CABECALHO_CSRF = '{CABECALHO_CSRF}'" in codigo
    # Só um ponto chama fetch: o helper que põe credentials e o cabeçalho de CSRF.
    assert len(re.findall(r"\bfetch\(", codigo)) == 1
