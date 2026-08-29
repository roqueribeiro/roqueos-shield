"""Health agregador — checa todas as dependências em paralelo.

`/health` simples (liveness, sem auth) — registrado direto em main.py.
`/health/full` (este router) — auth + checa Postgres/Redis/ZAP/LLM.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog
from fastapi import APIRouter

from orchestrator.api.deps import TokenDep
from orchestrator.config import settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


async def _check_postgres() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        from sqlalchemy import text

        from orchestrator.persistence.db import session

        async with session() as s:
            await s.exec(text("SELECT 1"))
        return _ok("postgres", t0)
    except Exception as e:  # noqa: BLE001
        return _down("postgres", t0, str(e))


async def _check_redis() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        from redis.asyncio import from_url

        client = from_url(settings.REDIS_URL, socket_connect_timeout=2.0)
        try:
            pong = await client.ping()
            if pong:
                return _ok("redis", t0)
            return _down("redis", t0, "ping returned False")
        finally:
            await client.aclose()
    except Exception as e:  # noqa: BLE001
        return _down("redis", t0, str(e))


async def _check_zap() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(
                f"{settings.ZAP_BASE_URL}/JSON/core/view/version/",
                params={"apikey": settings.ZAP_API_KEY},
            )
            if r.status_code == 200 and "version" in r.json():
                return _ok("zap", t0, detail={"version": r.json()["version"]})
            return _down("zap", t0, f"HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        return _down("zap", t0, str(e))


async def _check_llm_local() -> dict[str, Any]:
    """LM Studio / Ollama local — só checa se LLM_API_BASE setado."""
    t0 = time.perf_counter()
    if not settings.LLM_API_BASE:
        return {
            "name": "llm_local",
            "status": "disabled",
            "latency_ms": 0,
            "detail": {"reason": "LLM_API_BASE not set"},
        }
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{settings.LLM_API_BASE.rstrip('/')}/models")
            if r.status_code == 200:
                data = r.json()
                models = [m.get("id") for m in data.get("data", [])][:5]
                return _ok("llm_local", t0, detail={"models": models, "url": settings.LLM_API_BASE})
            return _down("llm_local", t0, f"HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        return _down("llm_local", t0, str(e))


async def _check_llm_cloud() -> dict[str, Any]:
    """Chave CONFIGURADA não é chave que funciona.

    Antes esta função devolvia `status: "ok"` só por existir uma variável preenchida
    — chave revogada, expirada ou com cota estourada aparecia igualzinho a uma chave
    boa. É o mesmo defeito do `health()` do censys ("construir cliente não faz
    round-trip"), e aqui não vale a isenção de contrato: isto não é `health()` de
    adapter, é o painel que o operador consulta para decidir se pode confiar.

    `configured` é um estado próprio, distinto de `ok`: dizemos o que sabemos.
    """
    keys = {
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "openai": bool(settings.OPENAI_API_KEY),
        "openrouter": bool(settings.OPENROUTER_API_KEY),
    }
    configuradas = [k for k, v in keys.items() if v]
    if not configuradas:
        return {
            "name": "llm_cloud",
            "status": "disabled",
            "latency_ms": 0,
            "detail": {"keys_configured": []},
        }
    return {
        "name": "llm_cloud",
        "status": "configured",
        "latency_ms": 0,
        "detail": {
            "keys_configured": configuradas,
            "note": "chave presente; NÃO verificada contra o provedor (uma chamada de "
            "teste custaria token a cada consulta de saúde). Chave revogada ou com "
            "cota estourada aparece aqui do mesmo jeito.",
        },
    }


async def _check_scanners() -> dict[str, Any]:
    """Os binários de scanner existem nesta imagem?

    O painel de saúde checava Postgres, Redis, ZAP e LLM — e NENHUM scanner. Ficava
    todo verde numa imagem sem nmap, sem trivy, sem semgrep: exatamente o estado em
    que os scans fecham com zero achados. É a pergunta mais direta que o operador
    tem, e não estava na tela.
    """
    import shutil

    esperados = {
        "nmap": "rede",
        "semgrep": "SAST (código)",
        "trivy": "CVE de dependência e imagem",
        "gitleaks": "segredo",
        "trufflehog": "segredo verificado",
        "checkov": "IaC",
        "nuclei": "template de CVE",
        "dnstwist": "typosquatting",
    }
    presentes = {n: shutil.which(n) is not None for n in esperados}
    faltando = sorted(n for n, ok in presentes.items() if not ok)
    return {
        "name": "scanners",
        "status": "ok" if not faltando else "degraded",
        "latency_ms": 0,
        "detail": {
            "presentes": sorted(n for n, ok in presentes.items() if ok),
            "ausentes": faltando,
            "note": (
                "todos os scanners esperados estão instalados"
                if not faltando
                else "scanner ausente NÃO roda e o vetor dele fica sem verificação: "
                + ", ".join(f"{n} ({esperados[n]})" for n in faltando)
            ),
        },
    }


def _ok(name: str, t0: float, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": "ok",
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "detail": detail or {},
    }


def _down(name: str, t0: float, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "down",
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "detail": {"error": reason[:200]},
    }


@router.get("/full")
async def health_full(_token: TokenDep) -> dict[str, Any]:
    """Checa Postgres, Redis, ZAP, LLM local + cloud em paralelo."""
    results = await asyncio.gather(
        _check_postgres(),
        _check_redis(),
        _check_zap(),
        _check_llm_local(),
        _check_llm_cloud(),
        _check_scanners(),
        return_exceptions=False,
    )
    statuses = [r["status"] for r in results]
    # `configured` (chave de nuvem presente mas não testada) não é degradação — é o
    # que sabemos dizer com honestidade. `degraded` de scanner ausente É, e tem que
    # subir para o topo: é a diferença entre a ferramenta rodar e a ferramenta
    # devolver zero achados por falta de binário.
    overall = "ok" if all(s in ("ok", "disabled", "configured") for s in statuses) else "degraded"
    return {"overall": overall, "components": results}
