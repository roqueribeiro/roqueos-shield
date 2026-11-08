"""Segredos do primeiro boot: gerados uma vez, 0600, o ambiente vence, e nada vaza.

O teste que importa é o último: roda o `main()` de verdade, captura toda a saída e
procura os valores gerados nela. Um `print(valor)` esquecido no módulo reprova aqui.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from orchestrator.standalone import segredos


def test_gera_uma_vez_e_reaproveita(tmp_path: Path) -> None:
    v1, o1 = segredos.garantir(tmp_path / "s", ambiente={})
    v2, o2 = segredos.garantir(tmp_path / "s", ambiente={})
    assert v1 == v2
    assert {o.de_onde for o in o1} == {"gerado"}
    assert {o.de_onde for o in o2} == {"arquivo"}
    assert len(v1["APP_TOKEN"]) == 64  # 32 bytes em hex


def test_arquivos_nascem_0600_e_pasta_0700(tmp_path: Path) -> None:
    pasta = tmp_path / "s"
    segredos.garantir(pasta, ambiente={})
    assert stat.S_IMODE(pasta.stat().st_mode) == 0o700
    for nome in segredos.SEGREDOS:
        assert stat.S_IMODE((pasta / nome).stat().st_mode) == 0o600, nome


def test_ambiente_vence_e_nao_grava_nada(tmp_path: Path) -> None:
    pasta = tmp_path / "s"
    valores, origens = segredos.garantir(pasta, ambiente={"APP_TOKEN": "do-cofre-123"})
    assert valores["APP_TOKEN"] == "do-cofre-123"  # noqa: S105  valor de fixture
    assert not (pasta / "APP_TOKEN").exists()
    assert [o.de_onde for o in origens if o.nome == "APP_TOKEN"] == ["ambiente"]


def test_secrets_key_e_chave_fernet_valida(tmp_path: Path) -> None:
    from cryptography.fernet import Fernet

    valores, _ = segredos.garantir(tmp_path / "s", ambiente={})
    f = Fernet(valores["SECRETS_KEY"].encode())
    assert f.decrypt(f.encrypt(b"x")) == b"x"


def test_arquivo_vazio_e_regerado(tmp_path: Path) -> None:
    pasta = tmp_path / "s"
    pasta.mkdir()
    (pasta / "APP_TOKEN").write_text("")
    valores, _ = segredos.garantir(pasta, ambiente={})
    assert valores["APP_TOKEN"]


def test_main_escreve_envdir_e_nao_imprime_valor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for nome in segredos.SEGREDOS:
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    envdir = tmp_path / "env"
    monkeypatch.setattr("sys.argv", ["segredos", str(envdir)])
    segredos.main()
    saida = capsys.readouterr()
    texto = saida.out + saida.err
    for nome in segredos.SEGREDOS:
        valor = (envdir / nome).read_text()
        assert valor, nome
        assert stat.S_IMODE((envdir / nome).stat().st_mode) == 0o600
        assert valor not in texto, f"o valor de {nome} apareceu na saída"
        assert f"segredo {nome}: gerado" in texto
