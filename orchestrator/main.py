"""FastAPI app factory.

Entrypoint: `uvicorn orchestrator.main:app --host 0.0.0.0 --port 8080`
ou via `make api`.

Serve também o dashboard UI em `/ui` (StaticFiles) + endpoints `/ui/api/*`.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from orchestrator import __version__
from orchestrator.ai.observability import log_processor
from orchestrator.api.routers import (
    audit as audit_router,
)
from orchestrator.api.routers import (
    auth as auth_router,
)
from orchestrator.api.routers import (
    conta as conta_router,
)
from orchestrator.api.routers import (
    exposure as exposure_router,
)
from orchestrator.api.routers import (
    findings as findings_router,
)
from orchestrator.api.routers import (
    health as health_router,
)
from orchestrator.api.routers import (
    investigate as investigate_router,
)
from orchestrator.api.routers import (
    mcp as mcp_router,
)
from orchestrator.api.routers import (
    reports as reports_router,
)
from orchestrator.api.routers import (
    scans as scans_router,
)
from orchestrator.api.routers import (
    settings as settings_router,
)
from orchestrator.api.routers import (
    system as system_router,
)
from orchestrator.api.routers import (
    targets as targets_router,
)
from orchestrator.api.routers import (
    ui as ui_router,
)
from orchestrator.api.routers import (
    users as users_router,
)
from orchestrator.config import settings
from orchestrator.domain.redaction import redaction_processor


def _setup_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redaction_processor,  # credencial nunca chega ao stdout nem ao SSE
            log_processor,  # ring buffer pra UI live logs
            (
                structlog.processors.JSONRenderer()
                if settings.LOG_FORMAT == "json"
                else structlog.dev.ConsoleRenderer()
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _setup_logging()
    log = structlog.get_logger(__name__)

    # SEC-01: fail-closed no boot se houver config insegura (ex.: APP_TOKEN de
    # exemplo, que concede ADMIN de serviço). Recusa subir em vez de servir aberto.
    from orchestrator.config import audit_is_mutable, insecure_boot_errors

    if audit_is_mutable(settings):
        log.warning(
            "audit.mutable_trail",
            detail="banco SQLite: o trigger append-only do audit_log é Postgres-only, "
            "então a trilha é editável. Em ambiente regulado use Postgres migrado e "
            "REQUIRE_IMMUTABLE_AUDIT=true.",
        )

    boot_errors = insecure_boot_errors(settings)
    if boot_errors:
        for err in boot_errors:
            log.error("boot.insecure_config", problem=err)
        raise RuntimeError(
            "Boot recusado por config insegura: "
            + "; ".join(boot_errors)
            + " (defina ALLOW_INSECURE_APP_TOKEN=true só em dev local)."
        )

    # cria tabelas (dev SQLite). Em prod usar `alembic upgrade head` antes.
    if settings.DATABASE_URL.startswith("sqlite"):
        from orchestrator.persistence.db import init_db

        await init_db()
        log.info("db.sqlite_init_done")

    # Configuração gravada pela tela (IA e escopo) por cima do ambiente. O que veio
    # no ambiente continua valendo; ver `orchestrator.runtime_settings`.
    try:
        from orchestrator.persistence.db import session as _db_session
        from orchestrator.runtime_settings import aplicar

        async with _db_session() as s:
            aplicadas = await aplicar(s)
        if aplicadas:
            log.info("settings.runtime_aplicadas", campos=aplicadas)
    except Exception as e:  # noqa: BLE001  banco sem a migration 0008 ainda
        log.warning("settings.runtime_indisponivel", error=str(e))

    # phoenix tracing opt-in
    if settings.PHOENIX_ENABLED and settings.PHOENIX_COLLECTOR_ENDPOINT:
        try:
            from orchestrator.ai.agentic.tracing import setup_phoenix

            if setup_phoenix(settings.PHOENIX_COLLECTOR_ENDPOINT):
                log.info("phoenix.tracing_enabled")
        except Exception as e:  # noqa: BLE001
            log.warning("phoenix.setup_failed", error=str(e))

    yield


_DESCRICAO = """
API do **RoqueShield**: teste contínuo de segurança com triagem de IA.

**Como autenticar.** Clique em *Authorize* e cole um token no `ApiToken`. Um admin cria
tokens por usuário em `POST /users` (ou na tela, em Usuários); o token aparece uma vez
só. A tela web usa um cookie de sessão próprio e não precisa disto.

**O contrato do silêncio.** Zero achado só quer dizer "limpo" quando
`coverage_complete` é `true`. Scanner que não rodou aparece em `scanners_skipped` com o
motivo, nunca como lista vazia.

Também: CLI `roqueshield`, servidor MCP em `/mcp` e o AI Fix Bundle em
`GET /reports/{scan_id}/ai-bundle`.
"""

_TAGS = [
    {"name": "conta", "description": "Primeiro uso e login por senha da tela."},
    {"name": "targets", "description": "Alvos autorizados."},
    {"name": "scans", "description": "Disparar, acompanhar e apagar scans."},
    {"name": "findings", "description": "Achados, fila de triagem e resolução."},
    {"name": "reports", "description": "Relatórios, conformidade e o AI Fix Bundle."},
    {"name": "investigate", "description": "Investigação de um achado pelo agente, sob a coleira."},
    {"name": "exposure", "description": "Exposição externa (OSINT)."},
    {"name": "settings", "description": "Configuração de IA e de escopo, sem reiniciar."},
    {"name": "system", "description": "Serviços, logs e uso do container."},
    {"name": "users", "description": "Usuários, papéis e tokens."},
    {"name": "auth", "description": "Login OIDC (SSO)."},
    {"name": "ui", "description": "Leituras agregadas que a tela usa, e o SSE de progresso."},
    {"name": "health", "description": "Saúde do serviço e de cada dependência."},
    {"name": "mcp", "description": "Servidor MCP (JSON-RPC) para agentes."},
]

app = FastAPI(
    title="RoqueShield API",
    description=_DESCRICAO,
    version=__version__,
    lifespan=lifespan,
    openapi_tags=_TAGS,
)

app.include_router(targets_router.router)
app.include_router(scans_router.router)
app.include_router(findings_router.router)
app.include_router(reports_router.router)
app.include_router(exposure_router.router)
app.include_router(investigate_router.router)
app.include_router(health_router.router)  # /health/full
app.include_router(ui_router.router)  # /ui/api/*
app.include_router(users_router.router)  # /users (admin-only, RBAC)
app.include_router(auth_router.router)  # /auth (OIDC SSO)
app.include_router(conta_router.router)  # /setup, /auth/session (senha, standalone)
app.include_router(settings_router.router)  # /settings/ai, /settings/scope
app.include_router(audit_router.router)  # /audit (audit:read, papel auditor)
app.include_router(system_router.router)  # /system/services, /system/logs, /system/usage
app.include_router(mcp_router.router)  # /mcp (MCP por HTTP)

# Session cookie pro state/nonce do fluxo OIDC (authlib usa request.session).
# Só montamos o SessionMiddleware quando o OIDC está realmente configurado — assim
# o engine NÃO exige `itsdangerous` (dep transitiva do middleware) quando SSO está
# desligado, que é o caso padrão (demo, self-host sem IdP). Import lazy de propósito.
if settings.OIDC_ISSUER and settings.OIDC_CLIENT_ID and settings.OIDC_CLIENT_SECRET:
    from starlette.middleware.sessions import SessionMiddleware

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET or settings.APP_TOKEN,
        same_site="lax",
        https_only=False,
    )

# Cabeçalhos de segurança da tela e da API. A CSP vale para a tela (tudo do mesmo
# endereço, nada de CDN). Ficam sem CSP só o /docs e o /redoc do FastAPI, que carregam
# o Swagger/ReDoc de CDN.
# `frame-ancestors 'none'` + X-Frame-Options valem para tudo: ninguém embute o shield.
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
# O dashboard antigo em /ui (só servido sem o build da tela) tem a CSP mais estrita da
# casa: libs vendorizadas em static/vendor, Alpine no build CSP (sem eval), Tailwind
# compilado em styles.css, nenhum script ou estilo inline. Até a issue #10 ele ficava
# isento, porque puxava Tailwind play-cdn (que exige 'unsafe-eval'), Alpine e Chart.js
# de CDN sem SRI, e guardava o token em localStorage.
_CSP_UI = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
_SEM_CSP = ("/docs", "/redoc")


def _csp_para(caminho: str) -> str | None:
    if caminho == "/ui" or caminho.startswith("/ui/"):
        return _CSP_UI
    if caminho.startswith(_SEM_CSP):
        return None
    return _CSP


class CabecalhosDeSeguranca:
    """ASGI puro (não `BaseHTTPMiddleware`): só acrescenta cabeçalhos no início da
    resposta e deixa o corpo passar como veio, sem bufferizar o SSE do progresso."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        csp = _csp_para(str(scope.get("path", "")))

        async def enviar(msg: Any) -> None:
            if msg["type"] == "http.response.start":
                nomes = {k.lower() for k, _ in msg.get("headers", [])}
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                ]
                if csp is not None:
                    extra.append((b"content-security-policy", csp.encode()))
                msg["headers"] = list(msg.get("headers", [])) + [
                    (k, v) for k, v in extra if k not in nomes
                ]
            await send(msg)

        await self.app(scope, receive, enviar)


app.add_middleware(CabecalhosDeSeguranca)


# A tela. Com o build da tela standalone (`web/`, saída em `orchestrator/web_dist`),
# ela é servida na raiz e o `/ui` antigo redireciona para lá. Sem o build (clone
# novo, imagem do RoqueOS antiga), fica o dashboard simples de antes em `/ui`.
# O mount na raiz vai por último: as rotas da API, registradas antes, casam primeiro.
_STATIC_DIR = Path(__file__).parent / "static"
_WEB_DIST = Path(__file__).parent / "web_dist"


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness simples (sem auth, leve). /health/full pra checagem completa."""
    return {"status": "ok", "version": app.version}


if (_WEB_DIST / "index.html").exists():

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/", include_in_schema=False)
    async def ui_antiga() -> RedirectResponse:
        return RedirectResponse(url="/", status_code=301)

    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")
else:
    if _STATIC_DIR.exists():
        app.mount("/ui", StaticFiles(directory=str(_STATIC_DIR), html=True), name="ui")

    # Fora do schema nos dois ramos: a fotografia do contrato (docs/openapi.json) não
    # pode depender de a tela ter sido buildada na máquina de quem gerou.
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Raiz redireciona pro dashboard."""
        return RedirectResponse(url="/ui/", status_code=302)
