"""Armazém de evidência endereçado por conteúdo (Frente C).

Um corpo de evidência vira um blob em `DATA_DIR/evidence/blobs/<2>/<sha256>`, nomeado
pelo hash do que é GRAVADO. Duas invariantes carregam o resto:

1. **Redige antes de gravar.** No modo default o corpo passa pelo `scrubber` ANTES de
   ser hasheado e escrito — o que fica em disco não tem CPF, PAN, token. O ARTEX grava
   tráfego em texto puro; isto é o oposto de propósito. O `original_sha256` (hash do
   corpo antes de redigir) fica no registro para proveniência, sem guardar o original.
   O modo cifrado (opção de engajamento, exige `SECRETS_KEY`) grava o original cifrado
   com Fernet em vez do redigido.
2. **Toda leitura confere o hash.** `get` recomputa o sha256 do que leu e recusa se não
   bater — um blob corrompido ou adulterado levanta, nunca volta calado. É o que separa
   evidência que se sustenta de um arquivo qualquer em disco.

O registro (`EvidenceSnapshotRow`) é write-once (trigger no Postgres, migration 0011); a
retenção apaga o CORPO (o arquivo) e mantém hash e registro — `get` de um corpo expurgado
levanta `EvidenceExpurgada`, que não é o mesmo que corrompido.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from orchestrator.config import settings
from orchestrator.domain.scrubber import scrub


class EvidenceIntegrityError(RuntimeError):
    """O corpo lido não bate com o hash que o endereça — corrompido ou adulterado."""


class EvidenceExpurgada(RuntimeError):
    """O corpo foi apagado pela retenção; o registro e o hash seguem no banco."""


@dataclass(frozen=True)
class BlobRef:
    sha256: str  # hash do conteúdo GRAVADO (redigido ou cifrado) — endereça o blob
    # Proveniência do original: HMAC-SHA256 com chave do servidor ("hmac-sha256:v1:<hex>"),
    # ou "" sem SECRETS_KEY. Nunca um SHA-256 puro (ver `_proveniencia`).
    original_sha256: str
    size_bytes: int
    encrypted: bool
    content_type: str


def _blobs_dir() -> Path:
    return settings.DATA_DIR / "evidence" / "blobs"


_SHA256 = re.compile(r"[0-9a-f]{64}")
_MARCA_DE_CORTE = "\n\n[... truncado em {n} caracteres ...]"


def _path(sha256: str) -> Path:
    # Defesa em profundidade: hoje toda chamada passa por um sha já lido do banco, mas o
    # caminho do disco não pode depender da ordem das chamadas para não aceitar `../`.
    if not _SHA256.fullmatch(sha256):
        raise EvidenceIntegrityError(f"endereço de blob inválido: {sha256[:80]!r}")
    return _blobs_dir() / sha256[:2] / sha256


def _proveniencia(original: bytes) -> str:
    """HMAC-SHA256 do corpo original, com chave derivada da SECRETS_KEY (separação de
    domínio). Um SHA-256 puro deixava descobrir o PII redigido por força bruta: o original
    só difere do redigido nos campos de baixa entropia que o scrubber trocou (CPF ~10^9,
    PAN ~10^5 por BIN com o Luhn, CVV 10^3). Sem SECRETS_KEY não há proveniência (""),
    nunca um hash quebrável."""
    chave = settings.SECRETS_KEY.strip()
    if not chave:
        return ""
    k = hashlib.sha256(b"roqueshield/evidence-provenance/v1\x00" + chave.encode()).digest()
    return "hmac-sha256:v1:" + hmac.new(k, original, hashlib.sha256).hexdigest()


def _cortar(texto: str, max_chars: int | None) -> str:
    if max_chars is None or len(texto) <= max_chars:
        return texto
    return texto[:max_chars] + _MARCA_DE_CORTE.format(n=max_chars)


def _cifrar(data: bytes) -> bytes:
    chave = settings.SECRETS_KEY.strip()
    if not chave:
        raise EvidenceIntegrityError(
            "EVIDENCE_ENCRYPT_ORIGINAL=true exige SECRETS_KEY (Fernet) — sem ela, só o "
            "modo redigido existe."
        )
    from cryptography.fernet import Fernet

    return Fernet(chave.encode()).encrypt(data)


def put(
    text: str,
    *,
    content_type: str = "text/plain",
    encrypt: bool | None = None,
    max_chars: int | None = None,
) -> BlobRef:
    """Guarda um corpo de evidência e devolve a referência (hashes, tamanho, modo).

    `encrypt=None` segue `settings.EVIDENCE_ENCRYPT_ORIGINAL`. `max_chars` corta o corpo
    DEPOIS do scrubber: cortar antes deixava o começo de um token ou de um PAN abaixo do
    tamanho que as regex reconhecem, e o pedaço ia para o disco em claro. Idempotente: o
    mesmo conteúdo gravado cai no mesmo caminho (mesmo sha) e não duplica o arquivo.
    """
    original = text.encode("utf-8", "replace")
    proveniencia = _proveniencia(original)

    usar_cifra = settings.EVIDENCE_ENCRYPT_ORIGINAL if encrypt is None else encrypt
    if usar_cifra:
        # Original cifrado; o sha endereça o ciphertext.
        gravado = _cifrar(_cortar(text, max_chars).encode("utf-8", "replace"))
    else:
        # Redige o corpo INTEIRO, só depois corta, e só então hasheia e grava.
        gravado = _cortar(scrub(text), max_chars).encode("utf-8", "replace")

    stored_sha = hashlib.sha256(gravado).hexdigest()
    destino = _path(stored_sha)
    if destino.exists():
        # Blob reaproveitado por outro snapshot: renova o mtime. O expurgo poupa blob
        # tocado há pouco, e assim não apaga o corpo de uma captura que ainda não comitou.
        os.utime(destino)
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        # Escrita atômica com temporário ÚNICO por escrita: com um `.tmp` fixo, dois
        # workers gravando o mesmo blob se atropelavam (um truncava o temporário enquanto
        # o outro renomeava) e o blob podia ficar com conteúdo parcial.
        tmp = destino.with_name(f".{destino.name}.{os.getpid()}.{uuid4().hex}.tmp")
        tmp.write_bytes(gravado)
        tmp.replace(destino)

    return BlobRef(
        sha256=stored_sha,
        original_sha256=proveniencia,
        size_bytes=len(gravado),
        encrypted=usar_cifra,
        content_type=content_type,
    )


def tocado_ha_menos_de(sha256: str, segundos: float) -> bool:
    """O blob foi gravado ou reaproveitado nos últimos `segundos`? (janela do expurgo)"""
    caminho = _path(sha256)
    return caminho.exists() and (time.time() - caminho.stat().st_mtime) < segundos


def get(sha256: str) -> bytes:
    """Lê o blob e CONFERE o hash. Corpo ausente → `EvidenceExpurgada`; hash que não
    bate → `EvidenceIntegrityError`. Nunca devolve conteúdo não verificado."""
    caminho = _path(sha256)
    if not caminho.exists():
        raise EvidenceExpurgada(f"corpo {sha256} não está em disco (expurgado ou nunca gravado)")
    data = caminho.read_bytes()
    real = hashlib.sha256(data).hexdigest()
    if real != sha256:
        raise EvidenceIntegrityError(
            f"blob {sha256} corrompido: o conteúdo em disco tem hash {real}"
        )
    return data


def _decifrar(data: bytes) -> bytes:
    chave = settings.SECRETS_KEY.strip()
    if not chave:
        raise EvidenceIntegrityError(
            "evidência cifrada, mas SECRETS_KEY ausente: não dá para recuperar o original."
        )
    from cryptography.fernet import Fernet, InvalidToken

    try:
        return Fernet(chave.encode()).decrypt(data)
    except InvalidToken as e:
        raise EvidenceIntegrityError(
            "não foi possível decifrar a evidência (SECRETS_KEY trocada?)."
        ) from e


def ler_claro(sha256: str, *, encrypted: bool) -> bytes:
    """Corpo em claro para o cliente autorizado: `get` (sempre confere o hash) e, se o
    blob for o original cifrado, decifra com a SECRETS_KEY. Sem isto, o modo cifrado
    devolveria ciphertext ilegível."""
    data = get(sha256)
    return _decifrar(data) if encrypted else data


def purge(sha256: str) -> bool:
    """Apaga o CORPO (o arquivo). Devolve True se havia o que apagar. O registro e o
    hash no banco não são tocados — a retenção é append-only como a auditoria."""
    caminho = _path(sha256)
    if caminho.exists():
        caminho.unlink()
        return True
    return False
