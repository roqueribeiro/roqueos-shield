"""Segredo em claro não sai do shield: scrubber, gitleaks, trufflehog e AI Fix Bundle.

Antes deste conserto:
- `scrub("token = ghp_...")` devolvia o token intacto (GitHub, Slack e `password=`
  não estavam na lista de padrões);
- o gitleaks punha o `Match` (segredo em claro) no `Evidence.snippet` e o `Secret`
  no `dedup_discriminator`;
- o trufflehog punha o `Raw` (a credencial) no snippet e no discriminador;
- o bundle mapeava semgrep para `infra`/`host_port` (arquivo em `host`, linha em
  `port`, contado como `patchable_automatically`) e só scrubbava a evidência.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from orchestrator.adapters.gitleaks_adapter import GitleaksAdapter
from orchestrator.adapters.trufflehog_adapter import TrufflehogAdapter
from orchestrator.domain.schemas import RawResults
from orchestrator.domain.scrubber import scrub
from orchestrator.persistence.models import FindingRow
from orchestrator.reporting.exporters.ai_bundle import _finding_to_vuln, _summary

# Valores sintéticos com o formato real de cada token. Montados por concatenação
# para o próprio arquivo de teste não disparar secret scanner.
GHP = "ghp" + "_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
GITHUB_PAT = "github_pat" + "_" + "11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz0123456789ABCDEF"
SLACK = "xoxb" + "-" + "123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx"


# --- 1. scrubber ---------------------------------------------------------------


@pytest.mark.parametrize("prefixo", ["ghp", "gho", "ghu", "ghs", "ghr"])
def test_scrub_redige_token_github_classico(prefixo: str) -> None:
    token = prefixo + "_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    out = scrub(f"token = {token}")
    assert token not in out
    assert "<GITHUB_TOKEN>" in out


def test_scrub_redige_github_fine_grained() -> None:
    out = scrub(f"export GH={GITHUB_PAT}")
    assert GITHUB_PAT not in out
    assert "<GITHUB_TOKEN>" in out


@pytest.mark.parametrize("letra", ["a", "b", "p", "r", "s"])
def test_scrub_redige_token_slack(letra: str) -> None:
    token = f"xox{letra}-" + "123456789012-AbCdEfGhIjKl"
    out = scrub(f"SLACK_TOKEN {token} fim")
    assert token not in out
    assert "<SLACK_TOKEN>" in out


@pytest.mark.parametrize(
    ("texto", "segredo"),
    [
        ("password=hunter2senha", "hunter2senha"),
        ("db_password: 's3nh@ forte'", "s3nh@ forte"),
        ('{"client_secret": "abc123xyz"}', "abc123xyz"),
        ("secret: valor-do-segredo", "valor-do-segredo"),
        ("PASSWD=Troca123", "Troca123"),
        ("GET /x?api_key=k3y-v4lor&page=2", "k3y-v4lor"),
        ("apiKey = 'qwerty987'", "qwerty987"),
    ],
)
def test_scrub_redige_atribuicao_de_segredo(texto: str, segredo: str) -> None:
    out = scrub(texto)
    assert segredo not in out, out
    assert "<REDACTED_SECRET>" in out


def test_scrub_atribuicao_preserva_resto_da_query() -> None:
    assert scrub("GET /x?api_key=k3y&page=2") == "GET /x?api_key=<REDACTED_SECRET>&page=2"


def test_scrub_atribuicao_nao_apaga_placeholder_especifico() -> None:
    # O JWT vira `<JWT>` primeiro; o padrão genérico não pode engolir o placeholder.
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.AAAA-BBBB_CCCC"
    assert scrub(f"secret={jwt}") == "secret=<JWT>"


def test_scrub_comparacao_nao_e_atribuicao() -> None:
    assert scrub("if password == expected:") == "if password == expected:"


# --- 2. gitleaks -----------------------------------------------------------------


def _item_gitleaks(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "RuleID": "github-pat",
        "Description": "GitHub Personal Access Token",
        "File": "config/settings.py",
        "StartLine": 12,
        "Commit": "0123456789abcdef0123",
        "Author": "dev",
        "Fingerprint": "0123456789abcdef0123:config/settings.py:github-pat:12",
    }
    base.update(extra)
    return base


def _normalize_gitleaks(item: dict[str, Any]) -> str:
    ad = GitleaksAdapter(gitleaks_bin="gitleaks", git_bin="git")
    findings = asyncio.run(ad.normalize(RawResults(adapter="gitleaks", payload=[item])))
    assert len(findings) == 1
    return findings[0].model_dump_json()


def test_gitleaks_roda_com_redact() -> None:
    import inspect

    from orchestrator.adapters import gitleaks_adapter

    src = inspect.getsource(gitleaks_adapter.GitleaksAdapter.start_scan)
    assert '"--redact"' in src


def test_gitleaks_report_sem_redact_nao_vaza_secret() -> None:
    # Report antigo ou gerado sem `--redact`: Match e Secret em claro.
    item = _item_gitleaks(Secret=GHP, Match=f"GITHUB_TOKEN = '{GHP}'")
    dump = _normalize_gitleaks(item)
    assert GHP not in dump
    assert "REDACTED" in dump


def test_gitleaks_report_redigido_segue_redigido() -> None:
    item = _item_gitleaks(Secret="REDACTED", Match="GITHUB_TOKEN = 'REDACTED'")  # noqa: S106
    dump = _normalize_gitleaks(item)
    assert "GITHUB_TOKEN = 'REDACTED'" in dump


def test_gitleaks_match_sem_secret_e_descartado() -> None:
    # Sem o Secret não há como saber onde está o segredo dentro do Match.
    item = _item_gitleaks(Match=f"token: {GHP[:4]}zzzzz-nao-reconhecido-zzzz")
    dump = _normalize_gitleaks(item)
    assert "nao-reconhecido" not in dump


def test_gitleaks_discriminador_nao_guarda_secret() -> None:
    item = _item_gitleaks(Secret=GHP, Match=GHP)
    item.pop("Fingerprint")
    item.pop("Commit")
    dump = _normalize_gitleaks(item)
    assert GHP not in dump
    assert "sha256:" in dump


# --- 3. trufflehog --------------------------------------------------------------


def _item_truffle(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "DetectorName": "Github",
        "Verified": False,
        "Raw": GHP,
        "SourceMetadata": {
            "Data": {"Git": {"file": "app.py", "line": 3, "commit": "abc123def456"}}
        },
    }
    base.update(extra)
    return base


def _normalize_truffle(item: dict[str, Any]) -> str:
    ad = TrufflehogAdapter()
    findings = asyncio.run(ad.normalize(RawResults(adapter="trufflehog", payload=[item])))
    assert len(findings) == 1
    return findings[0].model_dump_json()


def test_trufflehog_usa_redacted_e_nunca_raw() -> None:
    dump = _normalize_truffle(_item_truffle(Redacted="ghp_****"))
    assert GHP not in dump
    assert "ghp_****" in dump


def test_trufflehog_redacted_vazio_nao_cai_no_raw() -> None:
    dump = _normalize_truffle(_item_truffle(Redacted=""))
    assert GHP not in dump
    assert "valor omitido" in dump


def test_trufflehog_discriminador_nao_guarda_raw() -> None:
    item = _item_truffle(Redacted="")
    item["SourceMetadata"]["Data"]["Git"].pop("commit")
    dump = _normalize_truffle(item)
    assert GHP not in dump
    assert "sha256:" in dump


# --- 4. AI Fix Bundle ------------------------------------------------------------


def _row(tool: str, value: str, **payload: Any) -> FindingRow:
    return FindingRow(
        scan_id=uuid4(),
        target_id=uuid4(),
        deduped_key="k-" + tool,
        source_tool=tool,
        source_rule_id="regra",
        title=payload.pop("title", "achado"),
        severity="high",
        confidence="firm",
        payload={"target": {"asset_type": "repo", "value": value}, **payload},
    )


def test_bundle_semgrep_vira_sast_com_arquivo_e_linha() -> None:
    vuln = _finding_to_vuln(_row("semgrep", "src/db.py:41"))
    assert vuln["category"] == "sast"
    loc = vuln["instances"][0]["location"]
    assert loc == {"kind": "source_file", "path": "src/db.py", "line": 41}
    assert vuln["remediation"]["patch_strategy"]["approach"] == "code_change"
    resumo = _summary([vuln])
    assert resumo["patchable_automatically_count"] == 0
    assert resumo["needs_human_review_count"] == 1


def test_bundle_linha_ausente_fica_null() -> None:
    loc = _finding_to_vuln(_row("gitleaks", "app.py:?"))["instances"][0]["location"]
    assert loc["path"] == "app.py:?"
    assert loc["line"] is None


def test_bundle_scrubba_titulo_remediacao_e_triagem() -> None:
    row = _row(
        "zap",
        "http://alvo:3000",
        title=f"Token exposto {GHP}",
        remediation=f"Revogue {SLACK}",
        ai_triage={
            "rationale": f"vi password=hunter2senha e {GHP}",
            "business_impact": f"acesso via {SLACK}",
            "suggested_remediation": f"rotacione {GHP}",
            "model_used": "x",
        },
    )
    vuln = _finding_to_vuln(row)
    texto = repr(
        {
            "title": vuln["title"],
            "rule_name": vuln["discovered_by"]["rule_name"],
            "remediation": vuln["remediation"],
            "ai_triage": vuln["ai_triage"],
        }
    )
    for segredo in (GHP, SLACK, "hunter2senha"):
        assert segredo not in texto, segredo
    assert "<GITHUB_TOKEN>" in vuln["title"]


def test_bundle_scrubba_remediacao_do_scanner_sem_triagem() -> None:
    vuln = _finding_to_vuln(_row("checkov", "main.tf:3", remediation=f"use {SLACK}"))
    assert SLACK not in vuln["remediation"]["summary"]
