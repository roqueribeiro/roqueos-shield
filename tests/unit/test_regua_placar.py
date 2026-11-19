"""A régua de detecção mede certo? Cada regra do placar com o caso que a quebraria."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from orchestrator.domain.schemas import AssetType, Finding, Severity, Target
from orchestrator.regua.placar import (
    Gabarito,
    avaliar,
    comparar_com_linha_de_base,
    nova_linha_de_base,
)

RAIZ = "/srv/repo-da-regua"


def _gabarito() -> Gabarito:
    return Gabarito.model_validate(
        {
            "nome": "mini",
            "descricao": "gabarito de teste",
            "camadas": {"sast": {"scanners": ["semgrep"]}, "iac": {"scanners": ["checkov"]}},
            "itens": [
                {"id": "S1", "camada": "sast", "tipo": "defeito", "arquivo": "a.py",
                 "descricao": "sqli", "cwe": ["CWE-89"], "regra": "(?i)sql"},
                {"id": "S2", "camada": "sast", "tipo": "defeito", "arquivo": "b.py",
                 "descricao": "eval", "cwe": ["CWE-95"]},
                {"id": "I1", "camada": "iac", "tipo": "defeito", "arquivo": "s3.tf",
                 "descricao": "acl", "regra": "CKV_AWS_20\\b"},
                {"id": "L1", "camada": "sast", "tipo": "limpo", "arquivo": "ok.py",
                 "descricao": "limpo"},
            ],
        }
    )  # fmt: skip


def _f(tool: str, arquivo: str, regra: str, cwe: list[str] | None = None) -> Finding:
    return Finding(
        scan_id=uuid4(),
        target=Target(asset_type=AssetType.REPO, value=f"{RAIZ}/{arquivo}:3"),
        source_tool=tool,
        source_rule_id=regra,
        title=regra,
        description="d",
        severity=Severity.HIGH,
        cwe=cwe or [],
    )


def _tudo_certo() -> list[Finding]:
    return [
        _f("semgrep", "a.py", "tainted-sql-string", ["CWE-89"]),
        _f("semgrep", "b.py", "eval-detected", ["CWE-95"]),
        _f("checkov", "s3.tf", "CKV_AWS_20"),
    ]


def _avaliar(findings: list[Finding], ran: list[str] | None = None, skip=None):  # type: ignore[no-untyped-def]
    return avaliar(
        _gabarito(),
        findings,
        scanners_ran=ran if ran is not None else ["semgrep", "checkov"],
        scanners_skipped=skip or {},
        raiz=RAIZ,
    )


def test_placar_tudo_achado_pelo_motivo_certo() -> None:
    p = _avaliar(_tudo_certo())
    assert p.camadas["sast"].recall == 1.0
    assert p.camadas["sast"].classificacao == 1.0
    assert p.camadas["iac"].recall == 1.0
    assert p.camadas["sast"].falsos_positivos == 0


def test_placar_achado_no_arquivo_pelo_motivo_errado_nao_conta() -> None:
    # O checkov reclamar de versionamento no bucket não prova que viu a ACL pública.
    fs = [*_tudo_certo()[:2], _f("checkov", "s3.tf", "CKV_AWS_21")]
    p = _avaliar(fs)
    assert p.camadas["iac"].recall == 0.0
    assert p.camadas["iac"].nao_detectados == ["I1"]


def test_placar_achado_de_outra_camada_nao_conta() -> None:
    fs = [_f("gitleaks", "b.py", "generic", ["CWE-95"]), *_tudo_certo()[::2]]
    p = _avaliar(fs)
    assert p.camadas["sast"].nao_detectados == ["S2"]


def test_placar_cwe_errada_detecta_mas_nao_classifica() -> None:
    fs = [_f("semgrep", "a.py", "tainted-sql-string", ["CWE-704"]), *_tudo_certo()[1:]]
    p = _avaliar(fs)
    assert p.camadas["sast"].recall == 1.0
    assert p.camadas["sast"].classificacao == 0.5
    assert p.camadas["sast"].mal_classificados == ["S1"]


def test_placar_alarme_em_codigo_limpo_e_falso_positivo() -> None:
    p = _avaliar([*_tudo_certo(), _f("semgrep", "ok.py", "md5-used", ["CWE-327"])])
    assert p.camadas["sast"].falsos_positivos == 1


def test_placar_scanner_que_nao_rodou_deixa_a_camada_nao_medida() -> None:
    p = _avaliar(_tudo_certo()[:2], ran=["semgrep"], skip={"checkov": "binário ausente"})
    iac = p.camadas["iac"]
    assert not iac.medida
    assert iac.recall is None  # nem zero nem cem
    assert "binário ausente" in (iac.motivo_nao_medida or "")


def test_placar_achado_fora_do_gabarito_aparece() -> None:
    p = _avaliar([*_tudo_certo(), _f("semgrep", "outro.py", "x")])
    assert any("outro.py" in x for x in p.fora_do_gabarito)


_LINHA = {
    "mini": {
        "sast": {"recall_min": 1.0, "fp_max": 0, "classificacao_min": 1.0},
        "iac": {"recall_min": 1.0, "fp_max": 0},
    }
}


def test_linha_de_base_sem_regressao_passa() -> None:
    assert comparar_com_linha_de_base(_avaliar(_tudo_certo()), _LINHA, exigir_medida=True) == []


def test_linha_de_base_reprova_recall_fp_e_classificacao() -> None:
    fs = [
        _f("semgrep", "a.py", "tainted-sql-string", ["CWE-704"]),
        _f("semgrep", "ok.py", "md5"),
        _f("checkov", "s3.tf", "CKV_AWS_20"),
    ]
    problemas = comparar_com_linha_de_base(_avaliar(fs), _LINHA, exigir_medida=True)
    texto = " ".join(problemas)
    assert "recall caiu" in texto
    assert "falsos positivos subiram" in texto
    assert "classificação" in texto


def test_linha_de_base_nao_medida_reprova_so_quando_exigida() -> None:
    p = _avaliar(_tudo_certo()[:2], ran=["semgrep"], skip={"checkov": "ausente"})
    assert comparar_com_linha_de_base(p, _LINHA, exigir_medida=False) == []
    assert any("não medida" in x for x in comparar_com_linha_de_base(p, _LINHA, exigir_medida=True))


def test_linha_de_base_camada_nova_sem_registro_reprova() -> None:
    linha = {"mini": {"sast": _LINHA["mini"]["sast"]}}
    assert any("sem linha de base" in x for x in comparar_com_linha_de_base(
        _avaliar(_tudo_certo()), linha, exigir_medida=False
    ))  # fmt: skip


def test_catraca_nao_grava_piora() -> None:
    fs = [_tudo_certo()[0], _tudo_certo()[2]]  # S2 perdido
    nova, recusas = nova_linha_de_base(_avaliar(fs), _LINHA)
    assert nova["mini"]["sast"]["recall_min"] == 1.0
    assert any("piorou" in r for r in recusas)


def test_catraca_grava_melhora() -> None:
    linha = {
        "mini": {"sast": {"recall_min": 0.5, "fp_max": 3}, "iac": {"recall_min": 0.0, "fp_max": 0}}
    }
    nova, recusas = nova_linha_de_base(_avaliar(_tudo_certo()), linha)
    assert recusas == []
    assert nova["mini"]["sast"] == {"recall_min": 1.0, "fp_max": 0, "classificacao_min": 1.0}


def test_gabarito_real_carrega_e_cobre_as_tres_camadas() -> None:
    raiz = Path(__file__).resolve().parents[1] / "regua"
    g = Gabarito.carregar(raiz / "gabaritos" / "repo_sintetico.yaml")
    assert set(g.camadas) == {"sast", "iac", "segredo"}
    for item in g.itens:
        if item.camada == "segredo":
            continue  # gerados na hora pela régua, nunca commitados
        assert (raiz / "repo_sintetico" / item.arquivo).is_file(), item.arquivo
