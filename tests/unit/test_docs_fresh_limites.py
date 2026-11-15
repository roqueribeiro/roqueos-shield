"""O gate de docs vivas pega um "limite conhecido" que já não é limite.

Goal 0.1: a seção "Known limits" dizia "nenhuma rota lê o audit log", falso desde
que `GET /audit` entrou (orchestrator/api/routers/audit.py). O gate de docs não
pegava, porque só conhecia o caso do agente-stub. Este teste é o mutante do
mecanismo: com a rota existindo, a frase de volta no doc reprova; a árvore limpa
não reprova.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _carregar() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_docs_fresh_sob_teste", ROOT / "scripts" / "check_docs_fresh.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_rota_de_auditoria_existe_de_verdade() -> None:
    # A prova que faz o limite vencer: GET /audit está no código, ligado no main.
    mod = _carregar()
    assert mod._rota_de_auditoria_existe() is True


def test_arvore_limpa_nao_acusa_limite_vencido() -> None:
    # Depois do conserto, a frase saiu dos dois docs: nada a acusar.
    mod = _carregar()
    mod.FALHAS.clear()
    mod.check_limites_vencidos()
    assert [f for f in mod.FALHAS if "limite-vencido" in f] == []


def test_reprova_quando_a_frase_volta(monkeypatch) -> None:
    # Mutante: a frase vencida de volta no doc, com a rota existindo, reprova.
    mod = _carregar()
    real = mod._ler

    def falso(rel: str) -> str:
        if rel == "docs/ARCHITECTURE.md":
            return "## 15. Known limits\n- **No API reads the audit log.** in the database.\n"
        return real(rel)

    monkeypatch.setattr(mod, "_ler", falso)
    mod.FALHAS.clear()
    mod.check_limites_vencidos()
    acusacoes = [f for f in mod.FALHAS if "limite-vencido" in f]
    assert acusacoes, "a frase vencida voltou e o gate não reprovou"
    assert any("ARCHITECTURE.md:2" in f for f in acusacoes)
