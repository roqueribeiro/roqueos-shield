"""Freio de tentativa de login por senha.

Sem isto o scrypt (~40 ms) era o único freio: 30 senhas erradas seguidas davam 30
respostas 401, sem espera. Aqui cada chave (o e-mail tentado e o IP de origem) conta as
falhas; da quinta em diante a chave fica bloqueada por um tempo que dobra a cada falha
nova, de 30 s até 15 min. Um login certo zera o e-mail.

Mora em memória do processo da API, de propósito: o standalone e o compose de produção
rodam uma API só, e o bloqueio não pode depender do Redis estar de pé (o login por senha
funciona sem Redis). Reiniciar o container zera os contadores, o que é aceitável para um
freio de força bruta; não é trilha de auditoria (essa é o `user.login_failed`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

LIVRES = 5  # falhas sem bloqueio
PRIMEIRO_BLOQUEIO_S = 30.0
BLOQUEIO_MAX_S = 15 * 60.0
TETO_DE_CHAVES = 10_000  # memória limitada mesmo sob varredura de e-mails


@dataclass
class _Conta:
    falhas: int = 0
    livre_em: float = 0.0
    visto_em: float = 0.0


class Freio:
    def __init__(self, relogio=time.monotonic) -> None:
        self._relogio = relogio
        self._contas: dict[str, _Conta] = {}

    def espera(self, *chaves: str) -> float:
        """Segundos até poder tentar de novo (0 = pode)."""
        agora = self._relogio()
        return max(
            (self._contas[c].livre_em - agora for c in chaves if c in self._contas), default=0.0
        )

    def falhou(self, *chaves: str) -> None:
        agora = self._relogio()
        if len(self._contas) >= TETO_DE_CHAVES:
            self._podar(agora)
        for c in chaves:
            conta = self._contas.setdefault(c, _Conta())
            conta.falhas += 1
            conta.visto_em = agora
            if conta.falhas >= LIVRES:
                passo = conta.falhas - LIVRES
                conta.livre_em = agora + min(BLOQUEIO_MAX_S, PRIMEIRO_BLOQUEIO_S * 2**passo)

    def acertou(self, chave: str) -> None:
        self._contas.pop(chave, None)

    def _podar(self, agora: float) -> None:
        velhas = [c for c, v in self._contas.items() if v.livre_em <= agora]
        for c in velhas:
            del self._contas[c]
        if len(self._contas) >= TETO_DE_CHAVES:  # ainda cheio: sai o mais antigo
            for c, _ in sorted(self._contas.items(), key=lambda kv: kv[1].visto_em)[
                : len(self._contas) // 2
            ]:
                del self._contas[c]


freio = Freio()
