"""Os templates de adapter da skill, do agent e da regra passam no gate do silêncio.

Template é código que vai ser copiado. Se ele traz `except: return []` ou um `poll`
que decide só por `task.done()`, cada adapter novo nasce com o defeito que a regra 60
existe para impedir. Este teste roda as mesmas checagens do
`scripts/check_no_silence.py` sobre cada bloco ```python desses três arquivos, como se
fosse um arquivo de `orchestrator/adapters/`.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

RAIZ = Path(__file__).resolve().parents[2]
TEMPLATES = [
    RAIZ / ".claude" / "skills" / "cai-add-adapter" / "SKILL.md",
    RAIZ / ".claude" / "agents" / "adapter-author.md",
    RAIZ / ".claude" / "rules" / "scanners.md",
]
_BLOCO = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_no_silence", RAIZ / "scripts" / "check_no_silence.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _blocos(caminho: Path) -> list[str]:
    return [textwrap.dedent(b) for b in _BLOCO.findall(caminho.read_text(encoding="utf-8"))]


def _problemas(fonte: str, nome: str) -> list[str]:
    gate = _gate()
    # Caminho fictício DENTRO de orchestrator/adapters/: liga as regras mais duras do
    # gate (toda função conta, fetch_results que devolve vazio sem raise reprova).
    caminho = gate.DIR_ADAPTERS / f"_template_{nome}.py"
    arvore = ast.parse(fonte)
    return (
        gate._checar_excepts(caminho, fonte, arvore)
        + gate._checar_poll(caminho, arvore)
        + gate._checar_fetch_sem_saida_de_erro(caminho, fonte, arvore)
    )


@pytest.mark.parametrize("caminho", TEMPLATES, ids=lambda p: p.name)
def test_template_passa_no_gate_do_silencio(caminho: Path) -> None:
    blocos = _blocos(caminho)
    assert blocos, f"{caminho} não tem bloco python"
    for i, fonte in enumerate(blocos):
        assert _problemas(fonte, f"{caminho.stem}_{i}") == [], fonte


def test_skill_traz_o_template_completo() -> None:
    fonte = "\n".join(_blocos(TEMPLATES[0]))
    for sinal in (
        "ScanIntegrityError",
        "read_jsonl",
        "coverage_gaps",
        "task.result()",
        "tuple[int, Path]",
    ):
        assert sinal in fonte, sinal


@pytest.mark.parametrize("caminho", TEMPLATES, ids=lambda p: p.name)
def test_template_sem_os_padroes_antigos(caminho: Path) -> None:
    texto = caminho.read_text(encoding="utf-8")
    assert "return ScanStatus.DONE if task.done() else" not in texto
    assert "retornar lista vazia (não lança)" not in texto
    assert "—" not in texto


def test_gate_pega_o_template_antigo() -> None:
    """Mutação: o poll do template antigo tem que reprovar no mesmo caminho do teste."""
    antigo = textwrap.dedent(
        """
        class XyzAdapter:
            async def poll(self, handle):
                task = self._tasks.get(handle.native_id)
                if task is None:
                    return ScanStatus.FAILED
                return ScanStatus.DONE if task.done() else ScanStatus.RUNNING

            async def fetch_results(self, handle):
                try:
                    dados = json.loads(self._outs[handle.native_id].read_text())
                except json.JSONDecodeError:
                    return RawResults(adapter="xyz", payload=[])
                return RawResults(adapter="xyz", payload=dados)
        """
    )
    problemas = _problemas(antigo, "antigo")
    assert any("poll()" in p for p in problemas)
    assert any("except" in p for p in problemas)
