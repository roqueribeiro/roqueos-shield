"""O placar do OWASP Benchmark mede certo? Cada regra com o caso que a quebraria."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from orchestrator.domain.schemas import AssetType, Finding, Severity, Target
from orchestrator.regua.benchmark import (
    avaliar_benchmark,
    comparar_benchmark,
    ler_gabarito,
    linha_de_base_benchmark,
)

_CSV = """# test name, category, real vulnerability, cwe, Benchmark version: 0.1
BenchmarkTest00001,sqli,true,89
BenchmarkTest00002,sqli,false,89
BenchmarkTest00003,hash,true,328
BenchmarkTest00004,hash,false,328
"""


def _f(caso: str, cwe: list[str]) -> Finding:
    return Finding(
        scan_id=uuid4(),
        target=Target(asset_type=AssetType.REPO, value=f"/b/testcode/{caso}.py:12"),
        source_tool="semgrep",
        title="x",
        description="d",
        severity=Severity.HIGH,
        cwe=cwe,
    )


@pytest.fixture
def casos(tmp_path: Path):  # type: ignore[no-untyped-def]
    p = tmp_path / "expected.csv"
    p.write_text(_CSV, encoding="utf-8")
    return ler_gabarito(p)


def test_nota_e_acerto_menos_falso_positivo(casos) -> None:  # type: ignore[no-untyped-def]
    # Acerta o SQLi e cai na armadilha do SQLi; acerta o hash (CWE vizinha conta).
    p = avaliar_benchmark("t", casos, [
        _f("BenchmarkTest00001", ["CWE-89"]),
        _f("BenchmarkTest00002", ["CWE-89"]),
        _f("BenchmarkTest00003", ["CWE-327"]),
    ])  # fmt: skip
    assert p.categorias["sqli"].tpr == 1.0
    assert p.categorias["sqli"].fpr == 1.0
    assert p.categorias["sqli"].nota == 0.0  # marcar tudo é chutar
    assert p.categorias["hash"].nota == 1.0
    assert p.nota_media == 0.5


def test_cwe_de_outra_categoria_nao_conta(casos) -> None:  # type: ignore[no-untyped-def]
    # Achado no arquivo certo com a CWE errada não é acerto: ninguém ganha ponto por
    # reclamar de outra coisa no mesmo arquivo.
    p = avaliar_benchmark("t", casos, [_f("BenchmarkTest00001", ["CWE-79"])])
    assert p.categorias["sqli"].verdadeiros_positivos == 0
    assert "sqli" in p.sem_regra


def test_catraca_reprova_queda_e_aumento_de_falso_positivo(casos) -> None:  # type: ignore[no-untyped-def]
    bom = avaliar_benchmark("t", casos, [
        _f("BenchmarkTest00001", ["CWE-89"]),
        _f("BenchmarkTest00003", ["CWE-328"]),
    ])  # fmt: skip
    linha = linha_de_base_benchmark(bom)
    assert comparar_benchmark(bom, linha) == []
    pior = avaliar_benchmark("t", casos, [
        _f("BenchmarkTest00001", ["CWE-89"]),
        _f("BenchmarkTest00002", ["CWE-89"]),
    ])  # fmt: skip
    problemas = comparar_benchmark(pior, linha)
    assert any("nota média caiu" in x for x in problemas)
    assert any("falso positivo médio subiu" in x for x in problemas)
    assert comparar_benchmark(bom, None)  # sem linha de base não é verde


def test_gabarito_vazio_nao_mede_nada(tmp_path: Path) -> None:
    p = tmp_path / "vazio.csv"
    p.write_text("# só cabeçalho\n", encoding="utf-8")
    with pytest.raises(ValueError, match="vazio"):
        ler_gabarito(p)


def test_arredondamento_da_linha_de_base_nao_reprova_o_mesmo_placar(casos) -> None:  # type: ignore[no-untyped-def]
    # 1 acerto em 3 casos vira 0,3333 na linha de base; o placar igual não pode reprovar.
    p = avaliar_benchmark("t", casos, [_f("BenchmarkTest00001", ["CWE-89"])])
    assert comparar_benchmark(p, linha_de_base_benchmark(p)) == []
