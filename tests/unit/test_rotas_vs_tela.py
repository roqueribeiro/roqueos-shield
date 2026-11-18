"""Rota da API não pode morar onde a tela standalone serve arquivo estático.

A tela é montada em `/` (StaticFiles) DEPOIS dos routers, e o build do Vite serve o JS e
o CSS em `/assets/*` e as fontes em `/fonts/*`. Uma rota de API sob esses prefixos é
casada primeiro e devolve JSON (401/422) no lugar do bundle: a tela não carrega.

Foi o que aconteceu com o inventário de ativos (Frente A) em `/assets/{id}`: o e2e da
tela estourava timeout esperando `.entrada__ok`, passava na main e falhava no PR, e foi
lido como flaky. Este teste trava a classe inteira do defeito.

Nota sobre a primeira versão deste guarda: ela filtrava `app.routes` por `APIRoute`, mas
no FastAPI 0.141 os routers incluídos ficam como `_IncludedRouter` (não achatados), então
o filtro achava zero rotas e o teste passava vazio — revertido o conserto, seguia verde.
Por isso as duas checagens abaixo não dependem da estrutura interna de rotas.
"""

from __future__ import annotations

from pathlib import Path

import httpx

import orchestrator
from orchestrator.main import app

# Diretórios que o build do Vite gera em orchestrator/web_dist. Fixos aqui porque a suíte
# pode rodar sem o build; quando o build existe, os diretórios reais entram também.
_ESTATICOS_CONHECIDOS = {"assets", "fonts"}


def _estaticos_da_tela() -> list[str]:
    dist = Path(orchestrator.__file__).parent / "web_dist"
    reais = {p.name for p in dist.iterdir() if p.is_dir()} if dist.is_dir() else set()
    return sorted(_ESTATICOS_CONHECIDOS | reais)


def test_schema_nao_tem_rota_sob_estaticos_da_tela() -> None:
    caminhos = list(app.openapi()["paths"])
    colisoes = [
        c for c in caminhos for d in _estaticos_da_tela() if c == f"/{d}" or c.startswith(f"/{d}/")
    ]
    assert colisoes == [], f"rota de API sob diretório estático da tela: {colisoes}"


async def test_arquivo_estatico_nao_e_capturado_por_rota_da_api() -> None:
    # O que o navegador vê: pedir um arquivo do build não pode cair numa rota de API.
    # 200 (servido pelo StaticFiles) ou 404 (sem build) são aceitáveis; 401/403/422 é a
    # assinatura de uma rota de API respondendo no lugar do arquivo.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        for d in _estaticos_da_tela():
            resp = await client.get(f"/{d}/sonda-do-teste.js")
            assert resp.status_code in (200, 404), (
                f"/{d}/sonda-do-teste.js respondeu {resp.status_code} "
                f"({resp.headers.get('content-type')}): uma rota de API capturou o estático"
            )
