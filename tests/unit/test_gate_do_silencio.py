"""O gate também precisa de gate.

`check_no_silence.py` é o mecanismo que impede a volta do defeito mais caro deste
repositório. Uma auditoria adversarial conseguiu **burlá-lo de quatro formas** e
reintroduzir o silêncio no nmap com o gate em exit 0 e a suíte inteira verde. Um
controle que o autor do código consegue contornar em quatro tentativas não é
controle.

Cada caso abaixo é uma dessas burlas, virada teste. Se alguém "simplificar" o gate,
elas voltam a passar e isto reprova.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
ALVO = RAIZ / "orchestrator" / "adapters" / "nmap_adapter.py"


def _com_fetch(corpo: str) -> str:
    """Troca o `fetch_results` do nmap pelo corpo dado, MANTENDO a indentação.

    `textwrap.dedent` sozinho jogaria o método para o nível de módulo e quebraria a
    classe — o gate leria outra coisa e o teste provaria nada.
    """
    fonte = ALVO.read_text(encoding="utf-8")
    i = fonte.index("    async def fetch_results")
    j = fonte.index("\n    async def ", i + 10)
    corpo = textwrap.indent(textwrap.dedent(corpo).strip("\n"), "    ") + "\n"
    return fonte[:i] + corpo + fonte[j:]


def _rodar_gate() -> int:
    return subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "check_no_silence.py")],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        timeout=120,
    ).returncode


@pytest.fixture
def plantar():
    original = ALVO.read_text(encoding="utf-8")

    def _plantar(corpo: str) -> int:
        ALVO.write_text(_com_fetch(corpo), encoding="utf-8")
        return _rodar_gate()

    yield _plantar
    ALVO.write_text(original, encoding="utf-8")


def test_arvore_limpa_passa() -> None:
    assert _rodar_gate() == 0


def test_pega_raise_em_ramo_morto(plantar) -> None:
    """`if _ESTRITO: raise` com a flag desligada não é tratamento, é enfeite."""
    assert (
        plantar("""
        _ESTRITO = False

        async def fetch_results(self, handle: ScanHandle) -> RawResults:
            try:
                return RawResults(adapter=self.name, payload=self._ler(handle))
            except Exception:
                if _ESTRITO:
                    raise ScanIntegrityError("x")
                return RawResults(adapter=self.name, payload="")
        """)
        == 1
    )


def test_pega_append_em_lista_que_ninguem_le(plantar) -> None:
    """Registrar a lacuna numa lista local é fingir que registrou."""
    assert (
        plantar("""
        async def fetch_results(self, handle: ScanHandle) -> RawResults:
            descartes = []
            try:
                return RawResults(adapter=self.name, payload=self._ler(handle))
            except Exception as e:
                descartes.append(str(e))
                return RawResults(adapter=self.name, payload="")
        """)
        == 1
    )


def test_pega_silencio_movido_para_helper(plantar) -> None:
    """Não há grafo de chamada: por isso, num adapter, TODA função conta."""
    assert (
        plantar("""
        def _ler_report(self, handle):
            try:
                return self._ler(handle)
            except Exception:
                return ""

        async def fetch_results(self, handle: ScanHandle) -> RawResults:
            return RawResults(adapter=self.name, payload=self._ler_report(handle))
        """)
        == 1
    )


def test_pega_vazio_sem_except_nenhum(plantar) -> None:
    """A burla que nenhuma regra de `except` alcança."""
    assert (
        plantar("""
        async def fetch_results(self, handle: ScanHandle) -> RawResults:
            texto = self._ler(handle)
            return RawResults(adapter=self.name, payload=texto if texto.strip() else "")
        """)
        == 1
    )


def test_escape_declarado_e_aceito(plantar) -> None:
    """O `# silencio-ok` existe para o vazio que É o resultado certo.

    Nada entra por ele sem o motivo escrito — e o motivo escrito é o que denuncia um
    abuso na revisão.
    """
    assert (
        plantar("""
        async def fetch_results(self, handle: ScanHandle) -> RawResults:
            texto = self._ler(handle)
            # silencio-ok: teste do proprio escape
            return RawResults(adapter=self.name, payload=texto)
        """)
        == 0
    )
