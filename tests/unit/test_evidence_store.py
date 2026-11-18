"""Armazém de evidência — o corpo é redigido antes de gravar, e toda leitura confere o
hash (Frente C).

As duas invariantes que fazem a evidência se sustentar: o que vai para disco já passou
pelo scrubber (nada de PII em claro, ao contrário do ARTEX), e um corpo que não bate com
o hash que o endereça é recusado, nunca devolvido calado. Reverter qualquer uma reprova.
"""

from __future__ import annotations

import hashlib

import pytest

from orchestrator.config import settings
from orchestrator.evidence import store


@pytest.fixture
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    return tmp_path


def test_put_redige_corpo_antes_de_gravar(_data_dir) -> None:
    corpo = "login falhou para alvo@banco.com.br com senha=supersecreta"
    ref = store.put(corpo)
    gravado = store.get(ref.sha256).decode()
    # O que ficou em disco NÃO tem o e-mail nem o valor do segredo.
    assert "alvo@banco.com.br" not in gravado
    assert "supersecreta" not in gravado
    # O hash do original (proveniência) difere do hash do que foi gravado (redigido).
    assert ref.original_sha256 != ref.sha256


def test_get_confere_hash_e_recusa_corrompido(_data_dir) -> None:
    ref = store.put("conteúdo íntegro")
    # Adultera o arquivo no disco.
    caminho = store._path(ref.sha256)
    caminho.write_bytes(b"conteudo adulterado")
    with pytest.raises(store.EvidenceIntegrityError):
        store.get(ref.sha256)


def test_put_idempotente_mesmo_conteudo(_data_dir) -> None:
    a = store.put("mesmo corpo exato")
    b = store.put("mesmo corpo exato")
    assert a.sha256 == b.sha256
    # Um único arquivo para o mesmo conteúdo.
    arquivos = list((_data_dir / "evidence" / "blobs").rglob("*"))
    assert [p for p in arquivos if p.is_file()] == [store._path(a.sha256)]


def test_get_corpo_expurgado_levanta(_data_dir) -> None:
    ref = store.put("alvo de retenção")
    assert store.purge(ref.sha256) is True
    with pytest.raises(store.EvidenceExpurgada):
        store.get(ref.sha256)


def test_modo_cifrado_guarda_ciphertext_sem_plaintext(_data_dir, monkeypatch) -> None:
    from cryptography.fernet import Fernet

    chave = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "SECRETS_KEY", chave)

    corpo = "cartão 4111 1111 1111 1111 de alvo@banco.com.br"
    ref = store.put(corpo, encrypt=True)
    assert ref.encrypted is True

    gravado = store.get(ref.sha256)  # confere o hash do ciphertext
    assert b"banco.com.br" not in gravado
    # O ciphertext decifra de volta ao ORIGINAL (o modo cifrado preserva, não redige).
    assert Fernet(chave.encode()).decrypt(gravado).decode() == corpo
    assert ref.original_sha256 == hashlib.sha256(corpo.encode()).hexdigest()
