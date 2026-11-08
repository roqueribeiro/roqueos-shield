"""install.sh: o --help sob `curl | sh` e o ROQUESHIELD_NO_BROWSER só com 1/true/yes.

Roda o script de verdade (sh e bash). Para a leitura das variáveis, a última linha
(`main "$@"`) é trocada por uma sonda que chama só o `configurar` e imprime o
resultado: o corpo testado é o do arquivo, sem gancho de teste no instalador.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INSTALL = RAIZ / "install.sh"
SHELLS = [s for s in ("sh", "bash", "dash") if shutil.which(s)]


def _ambiente(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ROQUESHIELD_")}
    env.update({"LANG": "C", "LC_ALL": "C"})
    env.update(extra)
    return env


@pytest.mark.parametrize("shell", SHELLS)
def test_help_por_pipe_mostra_a_ajuda(shell: str) -> None:
    # `curl | sh`: o script chega pela entrada padrão e $0 é o próprio shell.
    r = subprocess.run(
        [shell, "-s", "--", "--help"],
        input=INSTALL.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        env=_ambiente(),
        timeout=20,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert "ROQUESHIELD_NO_BROWSER" in r.stdout
    assert "--update" in r.stdout
    # Não começou a instalar nada.
    assert "Checking Docker" not in r.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_help_por_arquivo_mostra_a_ajuda(shell: str) -> None:
    r = subprocess.run(
        [shell, str(INSTALL), "-h"],
        capture_output=True,
        text=True,
        env=_ambiente(),
        timeout=20,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert "ROQUESHIELD_PORT" in r.stdout


def _sonda(tmp_path: Path) -> Path:
    texto = INSTALL.read_text(encoding="utf-8")
    assert texto.rstrip().endswith('main "$@"'), "a última linha do install.sh mudou"
    corpo = texto.rstrip()[: -len('main "$@"')]
    sonda = tmp_path / "sonda.sh"
    sonda.write_text(corpo + 'configurar "$@"\nprintf "NAO_ABRIR=%s\\n" "$NAO_ABRIR"\n')
    return sonda


def _nao_abrir(tmp_path: Path, shell: str, *args: str, **env: str) -> str:
    r = subprocess.run(
        [shell, str(_sonda(tmp_path)), *args],
        capture_output=True,
        text=True,
        env=_ambiente(**env),
        timeout=20,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    linha = [x for x in r.stdout.splitlines() if x.startswith("NAO_ABRIR=")]
    assert linha, r.stdout
    return linha[-1].split("=", 1)[1]


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("valor", ["1", "true", "TRUE", "yes", "Yes"])
def test_no_browser_liga_so_com_valor_afirmativo(tmp_path: Path, shell: str, valor: str) -> None:
    assert _nao_abrir(tmp_path, shell, ROQUESHIELD_NO_BROWSER=valor) == "1"
    assert _nao_abrir(tmp_path, shell, ROQUESHIELD_NAO_ABRIR=valor) == "1"


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("valor", ["", "0", "false", "no", "sim-talvez"])
def test_no_browser_negativo_nao_desliga_o_navegador(
    tmp_path: Path, shell: str, valor: str
) -> None:
    assert _nao_abrir(tmp_path, shell, ROQUESHIELD_NO_BROWSER=valor) == "0"


@pytest.mark.parametrize("shell", SHELLS)
def test_flag_no_browser_continua_valendo(tmp_path: Path, shell: str) -> None:
    assert _nao_abrir(tmp_path, shell, "--no-browser", ROQUESHIELD_NO_BROWSER="0") == "1"
    assert _nao_abrir(tmp_path, shell, "--nao-abrir") == "1"
