from __future__ import annotations

from orchestrator.auth.senha import conferir, gerar_hash, problema_da_senha


def test_hash_confere_e_nao_guarda_em_claro() -> None:
    h = gerar_hash("uma senha boa demais")
    assert "uma senha boa" not in h
    assert conferir("uma senha boa demais", h)
    assert not conferir("uma senha boa demaiS", h)


def test_sal_diferente_a_cada_hash() -> None:
    assert gerar_hash("mesma-senha-123") != gerar_hash("mesma-senha-123")


def test_formato_estranho_nunca_lanca() -> None:
    for lixo in (None, "", "bcrypt$x", "scrypt$a$b$c$zz$yy", "scrypt$1$1$1$00"):
        assert conferir("qualquer", lixo) is False


def test_regra_da_senha() -> None:
    assert problema_da_senha("curta")
    assert problema_da_senha(" espaco-no-comeco")
    assert problema_da_senha("senha-com-dez") is None
