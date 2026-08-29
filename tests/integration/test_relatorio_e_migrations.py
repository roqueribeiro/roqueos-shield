"""Dois controles que ninguém estava exercitando: o HTML do relatório e o alembic.

O relatório é lido por um engenheiro de segurança de banco, servido inline pela API
e montado com conteúdo escolhido pelo ALVO ESCANEADO — entrada hostil por definição
numa ferramenta ofensiva. E as migrations são o que separa "trilha de auditoria
imutável" de uma tabela comum: se `alembic upgrade head` não chega no fim, o trigger
append-only da 0004 não existe.

Nenhum dos dois tinha teste. Os dois estavam quebrados.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Evidence,
    Finding,
    Severity,
    Target,
)
from orchestrator.jobs.pipelines import ScanResult

PAYLOAD = "<img src=x onerror=alert('xss')>"


def _resultado_com_payload() -> ScanResult:
    r = ScanResult(
        scan_id=uuid.uuid4(),
        target=Target(asset_type=AssetType.URL, value="https://app.test"),
    )
    r.findings.append(
        Finding(
            scan_id=r.scan_id,
            target=Target(asset_type=AssetType.URL, value="https://app.test/p"),
            source_tool="zap",
            source_rule_id="1",
            title=f"XSS refletido {PAYLOAD}",
            description=f"descricao {PAYLOAD}",
            severity=Severity.CRITICAL,
            confidence=Confidence.FIRM,
            evidence=[Evidence(description=f"evidencia {PAYLOAD}", snippet=PAYLOAD)],
        )
    )
    r.errors.append(f"gitleaks: {PAYLOAD}")
    r.scanners_skipped["gitleaks"] = f"binario ausente {PAYLOAD}"
    return r


@pytest.mark.parametrize("qual", ["tecnico", "executivo"])
def test_relatorio_escapa_html_vindo_do_alvo(qual: str, tmp_path: Path) -> None:
    """`select_autoescape(["html","xml"])` casa pelo SUFIXO do nome do template.

    Os arquivos se chamam `report.html.j2` e `executive.html.j2` — terminam em `.j2`.
    Medido (jinja2 3.1.6): autoescape **False** nos dois, True em `x.html`. Título de
    finding, `errors`, evidência e motivo de scanner pulado saíam CRUS.

    O executivo é servido como `HTMLResponse` inline, na MESMA origem da API e
    autenticado: um `<title>` malicioso na aplicação escaneada viraria script rodando
    como o analista, contra a API. E quem escolhe o conteúdo é o alvo.
    """
    from orchestrator.reporting.renderer import render_executive, render_html

    r = _resultado_com_payload()
    saida = tmp_path / f"{qual}.html"
    if qual == "tecnico":
        render_html(r, saida)
    else:
        render_executive(r, saida)
    html = saida.read_text(encoding="utf-8")

    # A marcação perigosa não pode existir como MARCAÇÃO. O texto escapado ainda
    # contém a sequência `onerror=alert(...)` dentro de `&lt;img ...&gt;`, e isso é
    # inerte — o que mata é a tag aberta.
    assert PAYLOAD not in html, "payload do alvo chegou CRU ao relatório"
    assert "<img src=x" not in html, "a tag <img> foi renderizada como marcação"
    assert "<script" not in html.replace("<script>", "@@")  # nenhum script injetado
    # e o conteúdo continua lá, escapado — o analista precisa VER o que o alvo mandou
    assert "&lt;img src=x" in html


def test_alembic_upgrade_head_num_banco_limpo(tmp_path: Path) -> None:
    """`alembic upgrade head` morria na 0002 e nunca chegava nas seguintes.

    A 0001 cria `scans.authorization_ref` com índice; a 0002 derruba a coluna via
    `batch_alter_table`, e o recreate do batch mode (SQLite) reflete e recria o índice
    órfão:

        sqlite3.OperationalError: no such column: authorization_ref
        [SQL: CREATE INDEX ix_scans_authorization_ref ON scans (authorization_ref)]

    Postgres não sofria (DROP COLUMN derruba o índice sozinho) e SQLite é o
    DATABASE_URL default. Ninguém via porque NENHUM teste rodava alembic — a suíte
    usa `init_db()`/`create_all`, que pula as migrations inteiras. E o que ficava
    para trás não era detalhe: a 0004 é quem cria o trigger append-only do
    `audit_log`, a garantia que o `REQUIRE_IMMUTABLE_AUDIT` exige.
    """
    db = tmp_path / "migrado.db"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[2],
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "DATABASE_URL": f"sqlite+aiosqlite:///{db}",
            "HOME": str(tmp_path),
        },
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"alembic falhou:\n{proc.stderr[-1500:]}"
    assert "0007" in proc.stderr or "0007" in proc.stdout, "não chegou na última migration"

    import sqlite3

    con = sqlite3.connect(db)
    colunas = {r[1] for r in con.execute("PRAGMA table_info(scans)")}
    tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert {"scanners_ran", "scanners_skipped", "errors"} <= colunas
    assert "audit_log" in tabelas, "a trilha de auditoria não foi criada"
