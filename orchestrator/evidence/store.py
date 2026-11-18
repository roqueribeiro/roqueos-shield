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
from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import settings
from orchestrator.domain.scrubber import scrub


class EvidenceIntegrityError(RuntimeError):
    """O corpo lido não bate com o hash que o endereça — corrompido ou adulterado."""


class EvidenceExpurgada(RuntimeError):
    """O corpo foi apagado pela retenção; o registro e o hash seguem no banco."""


@dataclass(frozen=True)
class BlobRef:
    sha256: str  # hash do conteúdo GRAVADO (redigido ou cifrado) — endereça o blob
    original_sha256: str  # hash do original (antes de redigir/cifrar) — proveniência
    size_bytes: int
    encrypted: bool
    content_type: str


def _blobs_dir() -> Path:
    return settings.DATA_DIR / "evidence" / "blobs"


def _path(sha256: str) -> Path:
    return _blobs_dir() / sha256[:2] / sha256


def _cifrar(data: bytes) -> bytes:
    chave = settings.SECRETS_KEY.strip()
    if not chave:
        raise EvidenceIntegrityError(
            "EVIDENCE_ENCRYPT_ORIGINAL=true exige SECRETS_KEY (Fernet) — sem ela, só o "
            "modo redigido existe."
        )
    from cryptography.fernet import Fernet

    return Fernet(chave.encode()).encrypt(data)


def put(text: str, *, content_type: str = "text/plain", encrypt: bool | None = None) -> BlobRef:
    """Guarda um corpo de evidência e devolve a referência (hashes, tamanho, modo).

    `encrypt=None` segue `settings.EVIDENCE_ENCRYPT_ORIGINAL`. Idempotente: o mesmo
    conteúdo gravado cai no mesmo caminho (mesmo sha) e não duplica o arquivo.
    """
    original = text.encode("utf-8", "replace")
    original_sha = hashlib.sha256(original).hexdigest()

    usar_cifra = settings.EVIDENCE_ENCRYPT_ORIGINAL if encrypt is None else encrypt
    if usar_cifra:
        gravado = _cifrar(original)  # original cifrado; o sha endereça o ciphertext
    else:
        gravado = scrub(text).encode("utf-8", "replace")  # redige ANTES de hashear/gravar

    stored_sha = hashlib.sha256(gravado).hexdigest()
    destino = _path(stored_sha)
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        # Escrita atômica: grava em .tmp e renomeia, para um leitor concorrente nunca ver
        # um arquivo cujo conteúdo ainda não casa com o nome (o hash).
        tmp = destino.with_suffix(".tmp")
        tmp.write_bytes(gravado)
        tmp.replace(destino)

    return BlobRef(
        sha256=stored_sha,
        original_sha256=original_sha,
        size_bytes=len(gravado),
        encrypted=usar_cifra,
        content_type=content_type,
    )


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


def purge(sha256: str) -> bool:
    """Apaga o CORPO (o arquivo). Devolve True se havia o que apagar. O registro e o
    hash no banco não são tocados — a retenção é append-only como a auditoria."""
    caminho = _path(sha256)
    if caminho.exists():
        caminho.unlink()
        return True
    return False
