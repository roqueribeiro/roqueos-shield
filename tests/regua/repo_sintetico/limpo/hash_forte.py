import hashlib


def digest(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()
