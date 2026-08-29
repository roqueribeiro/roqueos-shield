"""Prova de EFETIVIDADE: o pipeline inteiro contra um alvo com falhas reais.

Todo o resto da suíte prova que a ferramenta **não mente quando falha**. Este
arquivo responde a outra pergunta, que é a que um colega de banco faz primeiro:
*ela acha alguma coisa de verdade?* Sem isto, uma ferramenta que só levantasse
exceção passaria em tudo.

Monta um repositório com defeitos conhecidos (injeção de comando, SQL por
concatenação, desserialização de pickle, MD5, debug ligado, bucket S3 público,
security group aberto para 0.0.0.0/0, disco sem cifra), roda `run_scan` de ponta a
ponta e exige achado real de cada camada. Ao mesmo tempo confere o outro lado da
moeda: o scanner que NÃO está instalado tem que aparecer em `scanners_skipped` e
derrubar `coverage_is_complete`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.domain.schemas import AssetType, Target
from orchestrator.jobs.pipelines import run_scan

APP_VULNERAVEL = """
import hashlib
import pickle
import subprocess

import flask

app = flask.Flask(__name__)


@app.route("/ping")
def ping():
    host = flask.request.args.get("host")
    return subprocess.check_output("ping -c1 " + host, shell=True)


@app.route("/user")
def user(db):
    uid = flask.request.args.get("id")
    return db.execute("SELECT * FROM users WHERE id = '" + uid + "'")


@app.route("/load", methods=["POST"])
def load():
    return pickle.loads(flask.request.data)


def senha(p):
    return hashlib.md5(p.encode()).hexdigest()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
"""

IAC_VULNERAVEL = """
resource "aws_s3_bucket" "dados" {
  bucket = "dados-do-banco"
  acl    = "public-read"
}

resource "aws_security_group" "aberto" {
  name = "aberto"
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ebs_volume" "disco" {
  availability_zone = "us-east-1a"
  size              = 40
  encrypted         = false
}
"""


@pytest.fixture
def repo_vulneravel(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text(APP_VULNERAVEL, encoding="utf-8")
    (tmp_path / "main.tf").write_text(IAC_VULNERAVEL, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


@pytest.mark.skipif(
    shutil.which("semgrep") is None or shutil.which("checkov") is None,
    reason="precisa de semgrep e checkov instalados",
)
@pytest.mark.asyncio
async def test_pipeline_acha_falha_real_e_declara_o_que_nao_rodou(
    repo_vulneravel: Path,
) -> None:
    r = await run_scan(
        Target(asset_type=AssetType.REPO, value=str(repo_vulneravel)),
        skip_ai=True,
        scanners=["semgrep", "checkov", "gitleaks", "trivy", "trufflehog"],
    )

    por_tool: dict[str, int] = {}
    for f in r.findings:
        por_tool[f.source_tool] = por_tool.get(f.source_tool, 0) + 1

    # --- lado A: acha de verdade
    assert "semgrep" in r.scanners_ran, f"SAST não rodou; pulados={r.scanners_skipped}"
    assert por_tool.get("semgrep", 0) >= 5, f"SAST raso demais: {por_tool}"
    assert por_tool.get("checkov", 0) >= 3, f"IaC raso demais: {por_tool}"

    regras = {f.source_rule_id or "" for f in r.findings}
    texto = " ".join(regras)
    for esperado in ("subprocess", "sql", "deserialization", "md5"):
        assert esperado in texto.lower(), f"SAST não achou '{esperado}'. regras={regras}"
    assert any("CKV" in x for x in regras), "checkov não produziu nenhum CKV_*"

    altos = [f for f in r.findings if f.severity.value in ("high", "critical")]
    assert altos, "nenhum achado HIGH num app com injeção de comando"

    # --- lado B: o que não rodou é declarado (sem trivy/trufflehog na máquina)
    if shutil.which("trivy") is None:
        assert "trivy" in r.scanners_skipped
        assert not r.coverage_is_complete, "scanner ausente não pode dar cobertura completa"
        assert any("trivy" in e for e in r.errors)


@pytest.mark.skipif(shutil.which("semgrep") is None, reason="precisa de semgrep")
@pytest.mark.asyncio
async def test_semgrep_recusa_auto_em_vez_de_falhar_calado(repo_vulneravel: Path) -> None:
    """`--config auto` + `--metrics off` sai com erro e ZERO regras.

    Era o default do adapter: o único scanner que lê o código falhava em 100% das
    execuções, e antes da varredura do silêncio isso passava como scan concluído.
    """
    from orchestrator.adapters.semgrep_adapter import SemgrepAdapter

    ad = SemgrepAdapter()
    alvo = Target(asset_type=AssetType.REPO, value=str(repo_vulneravel))
    with pytest.raises(ValueError, match="metrics off|soberania|auto"):
        await ad.start_scan(alvo, {"config": "auto"})
