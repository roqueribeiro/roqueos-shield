"""Leva a saída de um processo do container para o Redis, para a tela ler ao vivo.

No RoqueOS quem lê o log de cada serviço é o `roqueos-server`, pelo Docker. No
container standalone não há Docker para ler (e montar o `docker.sock` daria root no
host a quem invadir o shield), então cada processo do supervisor escreve a saída por
aqui: a linha segue para o stdout de sempre (o `docker logs` continua funcionando) e
uma cópia, já com credencial redigida, vai para o stream `rs:logs:<serviço>` no Redis,
com teto de linhas.

O Redis fora do ar não derruba nada: a linha continua indo para o stdout, e o tee
tenta reconectar nas linhas seguintes.

Uso (no `run` do s6): `algum-processo 2>&1 | python -m orchestrator.standalone.logtee worker`
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from typing import Any, TextIO

from orchestrator.domain.redaction import redact_text

TETO = 5000
PREFIXO = "rs:logs:"


def chave(servico: str) -> str:
    return f"{PREFIXO}{servico}"


class Tee:
    def __init__(self, servico: str, cliente: Any | None, saida: TextIO) -> None:
        self.servico = servico
        self.cliente = cliente
        self.saida = saida
        self._proxima_tentativa = 0.0

    def linha(self, texto: str) -> None:
        texto = texto.rstrip("\n")
        self.saida.write(texto + "\n")
        self.saida.flush()
        if self.cliente is None or time.monotonic() < self._proxima_tentativa:
            return
        try:
            self.cliente.xadd(
                chave(self.servico),
                {"ts": datetime.now(UTC).isoformat(), "text": redact_text(texto)},
                maxlen=TETO,
                approximate=True,
            )
        except Exception:  # noqa: BLE001  Redis fora: o log local segue, e tenta de novo depois
            self._proxima_tentativa = time.monotonic() + 5


def main() -> None:
    servico = sys.argv[1] if len(sys.argv) > 1 else "desconhecido"
    cliente: Any | None
    try:
        from redis import Redis

        from orchestrator.config import settings

        cliente = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
    except Exception:  # noqa: BLE001
        cliente = None
    tee = Tee(servico, cliente, sys.stdout)
    for texto in sys.stdin:
        tee.linha(texto)


if __name__ == "__main__":
    main()
