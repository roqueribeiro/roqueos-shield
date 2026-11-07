"""Hash de senha com scrypt da biblioteca padrão.

scrypt e não bcrypt: o `passlib` com `bcrypt>=4.1` quebra na leitura da versão e
trunca senha acima de 72 bytes em silêncio. O `hashlib.scrypt` não tem nenhum dos
dois problemas e não puxa dependência.

Formato: `scrypt$<n>$<r>$<p>$<sal-hex>$<hash-hex>`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1
_DKLEN = 32
MIN_LEN = 10


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    dk = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${dk.hex()}"


def conferir(senha: str, guardado: str | None) -> bool:
    """True se `senha` bate com `guardado`. Nunca lança; formato estranho é False."""
    if not guardado:
        return False
    try:
        alg, n, r, p, sal_hex, dk_hex = guardado.split("$")
        if alg != "scrypt":
            return False
        dk = hashlib.scrypt(
            senha.encode("utf-8"),
            salt=bytes.fromhex(sal_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(dk_hex) // 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), dk_hex)


def problema_da_senha(senha: str) -> str | None:
    """Motivo para recusar a senha, ou None. Regra curta e explicável."""
    if len(senha) < MIN_LEN:
        return f"a senha precisa de pelo menos {MIN_LEN} caracteres"
    if senha.strip() != senha:
        return "a senha não pode começar nem terminar com espaço"
    return None
