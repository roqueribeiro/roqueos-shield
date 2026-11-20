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


def test_gabarito_real_carrega_e_cobre_todas_as_camadas() -> None:
    raiz = Path(__file__).resolve().parents[1] / "regua"
    g = Gabarito.carregar(raiz / "gabaritos" / "repo_sintetico.yaml")
    linguagens = {"js", "ts", "java", "go", "php", "ruby", "csharp"}
    assert set(g.camadas) == {"sast", "iac", "segredo", "dependencia"} | {
        f"sast_{x}" for x in linguagens
    }
    # Toda camada tem defeito plantado, e toda camada de SAST tem controle limpo:
    # sem limpo, uma ferramenta que marcasse tudo tiraria 100%.
    for camada in g.camadas:
        tipos = {i.tipo for i in g.itens if i.camada == camada}
        assert "defeito" in tipos, camada
        if camada.startswith("sast"):
            assert "limpo" in tipos, camada
    for item in g.itens:
        if item.camada == "segredo":
            continue  # gerados na hora pela régua, nunca commitados
        arquivo = raiz / "repo_sintetico" / item.arquivo
        # Manifesto de dependência fica com sufixo `.regua` (scripts/regua.py, desembrulhar).
        assert arquivo.is_file() or arquivo.with_name(arquivo.name + ".regua").is_file(), (
            item.arquivo
        )


def test_falso_positivo_cai_na_camada_do_controle_limpo() -> None:
    # Duas camadas com o mesmo scanner (o semgrep mede oito linguagens). O alarme no
    # controle limpo do Go é piora do Go, não do Python, que é a primeira camada do
    # semgrep. Mutação: atribuir sempre à primeira camada do scanner.
    g = Gabarito.model_validate(
        {
            "nome": "duas",
            "descricao": "x",
            "camadas": {"sast": {"scanners": ["semgrep"]}, "sast_go": {"scanners": ["semgrep"]}},
            "itens": [
                {"id": "LG", "camada": "sast_go", "tipo": "limpo", "arquivo": "ok.go",
                 "descricao": "limpo"},
            ],
        }
    )  # fmt: skip
    p = avaliar(
        g,
        [_f("semgrep", "ok.go", "md5")],
        scanners_ran=["semgrep"],
        scanners_skipped={},
        raiz=RAIZ,
    )
    assert p.camadas["sast_go"].falsos_positivos == 1
    assert p.camadas["sast"].falsos_positivos == 0


def _web(tool: str, url: str, regra: str, cwe: list[str] | None = None) -> Finding:
    return Finding(
        scan_id=uuid4(),
        target=Target(asset_type=AssetType.URL, value=url),
        source_tool=tool,
        source_rule_id=regra,
        title=regra,
        description="d",
        severity=Severity.HIGH,
        cwe=cwe or [],
    )


def test_alvo_web_compara_pelo_caminho_e_limpo_tipado_so_conta_o_seu_alarme() -> None:
    # Achado de URL vale pelo caminho (sem host nem query); nmap pela porta. E o controle
    # limpo com CWE só conta o alarme daquele tipo: o aviso de cabeçalho ausente que toda
    # página recebe não é falso positivo de XSS. Mutação: tirar o filtro `alarmes`.
    g = Gabarito.model_validate(
        {
            "nome": "web",
            "descricao": "x",
            "camadas": {"dast": {"scanners": ["zap"]}, "rede": {"scanners": ["nmap"]}},
            "itens": [
                {"id": "X1", "camada": "dast", "tipo": "defeito", "arquivo": "/busca",
                 "descricao": "xss", "cwe": ["CWE-79"]},
                {"id": "L1", "camada": "dast", "tipo": "limpo", "arquivo": "/busca-segura",
                 "descricao": "escapa", "cwe": ["CWE-79"]},
                {"id": "P1", "camada": "rede", "tipo": "defeito", "arquivo": "porta/8088/tcp",
                 "descricao": "porta http"},
            ],
        }
    )  # fmt: skip
    achados = [
        _web("zap", "http://alvo:8088/busca?q=%3Cscript%3E", "40012", ["CWE-79"]),
        _web("zap", "http://alvo:8088/busca-segura?q=x", "10038", ["CWE-693"]),
        Finding(
            scan_id=uuid4(),
            target=Target(asset_type=AssetType.PORT, value="10.0.0.5:8088/tcp"),
            source_tool="nmap",
            source_rule_id="nmap-open-port",
            title="porta aberta",
            description="d",
            severity=Severity.INFO,
        ),
    ]
    p = avaliar(g, achados, scanners_ran=["zap", "nmap"], scanners_skipped={})
    assert p.camadas["dast"].recall == 1.0
    assert p.camadas["dast"].falsos_positivos == 0
    assert p.camadas["rede"].recall == 1.0
    # O XSS na busca segura, esse sim, é falso positivo.
    achados.append(_web("zap", "http://alvo:8088/busca-segura?q=y", "40012", ["CWE-79"]))
    p = avaliar(g, achados, scanners_ran=["zap", "nmap"], scanners_skipped={})
    assert p.camadas["dast"].falsos_positivos == 1


def test_caminho_com_barra_dupla_do_nuclei_casa_com_o_gabarito() -> None:
    # Mutação: tirar o re.sub das barras -> o caminho com barra dupla não casa.
    g = Gabarito.model_validate(
        {
            "nome": "w",
            "descricao": "x",
            "camadas": {"dast_nuclei": {"scanners": ["nuclei"]}},
            "itens": [
                {"id": "N", "camada": "dast_nuclei", "tipo": "defeito", "arquivo": "/.env",
                 "descricao": "arquivo de ambiente exposto", "regra": "generic"},
            ],
        }
    )  # fmt: skip
    p = avaliar(
        g,
        [_web("nuclei", "http://alvo:8088//.env", "generic-env")],
        scanners_ran=["nuclei"],
        scanners_skipped={},
    )
    assert p.camadas["dast_nuclei"].recall == 1.0


def test_dois_tercos_nao_reprova_contra_ele_mesmo_gravado() -> None:
    # 2/3 gravado com 4 casas é 0,6667, acima de 0,666...: sem folga, reprovava sozinho.
    fs = [_f("semgrep", "a.py", "tainted-sql-string", ["CWE-89"])]
    p = _avaliar(fs)
    nova, _ = nova_linha_de_base(p, {})
    assert comparar_com_linha_de_base(p, nova, exigir_medida=True) == []


def test_lugar_com_asterisco_casa_por_prefixo() -> None:
    # `/api-docs*` pega o `swagger.json` que o nuclei acha embaixo; o resto não.
    g = Gabarito.model_validate(
        {
            "nome": "w",
            "descricao": "x",
            "camadas": {"dast_nuclei": {"scanners": ["nuclei"]}},
            "itens": [
                {"id": "S", "camada": "dast_nuclei", "tipo": "defeito", "arquivo": "/api-docs*",
                 "descricao": "swagger", "regra": "swagger"},
            ],
        }
    )  # fmt: skip
    achado = [_web("nuclei", "http://j:3000/api-docs/swagger.json", "swagger-api")]
    p = avaliar(g, achado, scanners_ran=["nuclei"], scanners_skipped={})
    assert p.camadas["dast_nuclei"].recall == 1.0
    assert p.fora_do_gabarito == []
    outro = [_web("nuclei", "http://j:3000/apidocs", "swagger-api")]
    assert (
        avaliar(g, outro, scanners_ran=["nuclei"], scanners_skipped={})
        .camadas["dast_nuclei"]
        .recall
        == 0.0
    )


def test_manifesto_de_dependencia_nao_fica_com_o_nome_de_verdade_no_repositorio() -> None:
    # Este repo é público: com o nome de verdade, o grafo de dependências do GitHub lê o
    # Log4Shell plantado e põe alerta crítico na página do projeto.
    raiz = Path(__file__).resolve().parents[1] / "regua" / "repo_sintetico"
    reais = {"package-lock.json", "package.json", "pom.xml", "go.mod", "go.sum",
             "requirements.txt", "Gemfile.lock", "yarn.lock", "Pipfile.lock"}  # fmt: skip
    assert [p for p in raiz.rglob("*") if p.name in reais] == []


def test_desembrulhar_devolve_o_nome_que_o_trivy_le(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "regua", Path(__file__).resolve().parents[2] / "scripts" / "regua.py"
    )
    assert spec and spec.loader
    regua = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regua)
    (tmp_path / "deps").mkdir()
    (tmp_path / "deps" / "pom.xml.regua").write_text("<project/>")
    regua.desembrulhar(tmp_path)
    assert (tmp_path / "deps" / "pom.xml").read_text() == "<project/>"
    assert not list(tmp_path.rglob("*.regua"))
