"""Rate limit das rotas que disparam trabalho caro (Issue #11, item a).

`POST /scans`, `POST /exposure/scan` e `POST /investigate/{id}` enfileiram scanner
ativo ou chamada de LLM. Sem teto, um token vazado (ou um laço num cliente) enchia a
fila do worker e a conta do provedor de IA. Janela fixa por principal e por rota.

Usa o Redis que o arq já exige, sem dependência nova. Se o Redis não responder, cai
num contador em memória do processo: o limite continua valendo por réplica, em vez
de desligar a proteção junto com o Redis.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import HTTPException, status

from orchestrator.api.deps import PrincipalDep
from orchestrator.config import settings

log = structlog.get_logger(__name__)

_memoria: dict[str, tuple[int, float]] = {}
_redis = None


async def _contar_no_redis(chave: str, janela: int) -> int:
    global _redis
    if _redis is None:
        from redis.asyncio import from_url

        _redis = from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
    pipe = _redis.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, janela, nx=True)
    contagem, _ = await pipe.execute()
    return int(contagem)


def _contar_na_memoria(chave: str, janela: int) -> int:
    agora = time.monotonic()
    contagem, inicio = _memoria.get(chave, (0, agora))
    if agora - inicio >= janela:
        contagem, inicio = 0, agora
    _memoria[chave] = (contagem + 1, inicio)
    return contagem + 1


ContarFn = Callable[[str, int], Awaitable[int]]


def rate_limit(rota: str, *, janela: int = 60) -> Callable[..., Awaitable[None]]:
    """Dependência: até `RATE_LIMIT_PER_MINUTE` chamadas por principal na janela.

    `RATE_LIMIT_PER_MINUTE=0` desliga (ex.: carga controlada em lab).
    """

    async def dependencia(principal: PrincipalDep) -> None:
        limite = settings.RATE_LIMIT_PER_MINUTE
        if limite <= 0:
            return
        janela_atual = int(time.time()) // janela
        chave = f"ratelimit:{rota}:{principal.id}:{janela_atual}"
        try:
            contagem = await _contar_no_redis(chave, janela)
        except Exception as e:  # noqa: BLE001 — Redis fora não pode desligar o limite
            log.warning("ratelimit.redis_unavailable", error=str(e))
            contagem = _contar_na_memoria(chave, janela)
        if contagem > limite:
            espera = janela - int(time.time()) % janela
            log.warning("ratelimit.exceeded", rota=rota, principal=principal.id, limite=limite)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"limite de {limite} chamadas por minuto em {rota}",
                headers={"Retry-After": str(espera)},
            )

    return dependencia
