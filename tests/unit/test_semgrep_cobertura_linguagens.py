"""SAST fora do Python: o que a régua de detecção multi-linguagem achou no adapter.

Três defeitos, medidos contra o ruleset de produção (imagem v0.7.2) em 20/11/2026:

1. Projeto só de TypeScript rodava as 13 regras da pasta `typescript` e saía com ZERO
   achados: as regras que pegam TS moram na pasta `javascript`.
2. Injeção de comando em Java (`Runtime.exec`) e C# (`Process.Start`) e TLS sem
   verificação em Go: nenhuma regra do pacote pinado pegava pelo motivo certo. As
   regras próprias (`regras_semgrep/roqueshield.yaml`) fecham as três.
3. Execução de comando do Go, Ruby e PHP saía como CWE-94 (injeção de código), e o
   `eval` do PHP como CWE-78: a CWE errada tira o achado da linha certa do relatório.

Antes das correções a régua dava Java 80%, Go 50%, PHP 75%, Ruby 67% e C# 67%.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orchestrator.adapters import semgrep_adapter as sa

_P = "opt.semgrep-rules."  # prefixo do check_id com o ruleset embarcado


def _ruleset_falso(raiz: Path) -> Path:
    for ling in ("javascript", "typescript", "python", "generic", "go"):
        (raiz / ling).mkdir(parents=True)
    return raiz


def test_projeto_so_typescript_carrega_as_regras_de_javascript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutação: tirar o `querer | {"javascript"}` -> só `typescript` e `generic`.
    regras = _ruleset_falso(tmp_path / "regras")
    monkeypatch.setenv("SEMGREP_RULES_DIR", str(regras))
    app = tmp_path / "app"
    (app / "src").mkdir(parents=True)
    (app / "src" / "rota.ts").write_text("export const x = 1\n")
    nomes = {Path(c).name for c in sa._configs_locais(app)}
    assert nomes == {"generic", "javascript", "typescript"}


def test_projeto_so_javascript_nao_ganha_typescript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    regras = _ruleset_falso(tmp_path / "regras")
    monkeypatch.setenv("SEMGREP_RULES_DIR", str(regras))
    app = tmp_path / "app"
    app.mkdir()
    (app / "index.js").write_text("module.exports = 1\n")
    assert {Path(c).name for c in sa._configs_locais(app)} == {"generic", "javascript"}


def test_regras_proprias_vao_em_todo_scan_sem_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutação: tirar o append de DIR_REGRAS_PROPRIAS -> a lista para no ruleset local.
    regras = _ruleset_falso(tmp_path / "regras")
    monkeypatch.setenv("SEMGREP_RULES_DIR", str(regras))
    app = tmp_path / "app"
    app.mkdir()
    (app / "main.go").write_text("package main\n")
    configs = sa._resolver_configs(None, app)
    assert configs[-1] == str(sa.DIR_REGRAS_PROPRIAS)
    # E também quando não há ruleset local (packs do registry).
    monkeypatch.setenv("SEMGREP_RULES_DIR", str(tmp_path / "nao-existe"))
    assert sa._resolver_configs(None, app) == [*sa._DEFAULT_CONFIGS, str(sa.DIR_REGRAS_PROPRIAS)]


def test_config_explicito_nao_ganha_regras_proprias() -> None:
    # Quem pediu um config específico recebe exatamente ele.
    assert sa._resolver_configs("/regras/minhas") == ["/regras/minhas"]


def test_regras_proprias_existem_e_cobrem_as_lacunas_medidas() -> None:
    doc = yaml.safe_load((sa.DIR_REGRAS_PROPRIAS / "roqueshield.yaml").read_text())
    por_id = {r["id"]: r for r in doc["rules"]}
    assert set(por_id) == {
        "roqueshield.java.comando-montado-por-concatenacao",
        "roqueshield.csharp.comando-montado-por-concatenacao",
        "roqueshield.go.tls-sem-verificacao-de-certificado",
        # Do OWASP Benchmark Python: weakrand de 0 para 99/99, xss de -28% para -6%.
        "roqueshield.python.aleatorio-previsivel",
        "roqueshield.python.flask-resposta-com-entrada-sem-escapar",
    }
    cwe = {i: sa._extract_cwes(r["metadata"]["cwe"]) for i, r in por_id.items()}
    assert cwe["roqueshield.java.comando-montado-por-concatenacao"] == ["CWE-78"]
    assert cwe["roqueshield.csharp.comando-montado-por-concatenacao"] == ["CWE-78"]
    assert cwe["roqueshield.go.tls-sem-verificacao-de-certificado"] == ["CWE-295"]
    assert cwe["roqueshield.python.aleatorio-previsivel"] == ["CWE-330"]
    assert cwe["roqueshield.python.flask-resposta-com-entrada-sem-escapar"] == ["CWE-79"]


@pytest.mark.parametrize(
    ("check_id", "do_pacote", "esperada"),
    [
        (
            _P + "go.lang.security.audit.dangerous-exec-command.dangerous-exec-command",
            ["CWE-94"],
            "CWE-78",
        ),
        (_P + "ruby.lang.security.dangerous-exec.dangerous-exec", ["CWE-94"], "CWE-78"),
        (_P + "php.lang.security.tainted-exec.tainted-exec", ["CWE-94"], "CWE-78"),
        (_P + "php.lang.security.exec-use.exec-use", ["CWE-94"], "CWE-78"),
        (_P + "php.lang.security.eval-use.eval-use", ["CWE-78"], "CWE-95"),
    ],
)
def test_execucao_de_comando_e_eval_saem_com_a_cwe_certa_na_frente(
    check_id: str, do_pacote: list[str], esperada: str
) -> None:
    # Mutação: tirar as linhas de CWE-78/CWE-95 de _CWE_CORRETA_POR_REGRA.
    cwes = sa._corrigir_cwes(check_id, do_pacote)
    assert cwes[0] == esperada
    assert set(do_pacote) <= set(cwes)  # a do pacote fica


def test_eval_do_javascript_nao_vira_cwe_78() -> None:
    # A correção do eval é só do PHP: o eval do JS já vem certo (CWE-95).
    check = _P + "javascript.browser.security.eval-detected.eval-detected"
    assert sa._corrigir_cwes(check, ["CWE-95"]) == ["CWE-95"]
