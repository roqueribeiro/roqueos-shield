"""A CWE de injeção de SQL do semgrep: a regra vem do pacote com a CWE errada.

`python.flask.security.injection.tainted-sql-string` traz na metadata uma CWE de
conversão de tipo. É a CWE que vira a categoria OWASP/PCI/LGPD do relatório; sem a
correção, a injeção de SQL sai classificada como outra coisa. Medido pela régua de
detecção (classificação 90% sem o conserto, 100% com ele).
"""

from __future__ import annotations

from orchestrator.adapters.semgrep_adapter import SemgrepAdapter, _corrigir_cwes
from orchestrator.domain.schemas import RawResults


def _payload(check_id: str, cwe: list[str]) -> dict[str, object]:
    return {
        "results": [
            {
                "check_id": check_id,
                "path": "app/db.py",
                "start": {"line": 7},
                "extra": {
                    "message": "SQL montado com entrada do usuário",
                    "severity": "ERROR",
                    "lines": "cur.execute('SELECT * FROM u WHERE id=' + uid)",
                    "metadata": {"cwe": cwe},
                },
            }
        ]
    }


async def test_semgrep_tainted_sql_sai_com_cwe_89_na_frente() -> None:
    raw = RawResults(
        adapter="semgrep",
        payload=_payload(
            "python.flask.security.injection.tainted-sql-string.tainted-sql-string",
            ["CWE-704: Incorrect Type Conversion or Cast"],
        ),
    )
    (f,) = await SemgrepAdapter().normalize(raw)
    assert f.cwe[0] == "CWE-89"
    assert "CWE-704" in f.cwe  # a do pacote fica: não apagamos informação


async def test_semgrep_regra_sem_correcao_mantem_a_cwe_do_pacote() -> None:
    raw = RawResults(
        adapter="semgrep",
        payload=_payload(
            "python.lang.security.audit.eval-detected.eval-detected", ["CWE-95: Eval"]
        ),
    )
    (f,) = await SemgrepAdapter().normalize(raw)
    assert f.cwe == ["CWE-95"]


def test_corrigir_cwes_nao_duplica_quando_ja_vem_certa() -> None:
    assert _corrigir_cwes("x.sql-injection", ["CWE-89"]) == ["CWE-89"]
