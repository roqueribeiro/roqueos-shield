"""A cobertura tem que CHEGAR à linha do scan — e daí à API, ao bundle e ao relatório.

Este arquivo existe por causa de uma falha de verificação, não de código. A varredura
do silêncio consertou nove adapters para que "não rodou" deixasse de parecer "não
achou", e o teste que travava isso montava o scan com
`SimpleNamespace(requested_scanners=[...], errors=[...])`.

O problema: `ScanRow.errors` **nunca era gravado**. O `_persist_findings` escrevia
`state=done` e as findings, e mais nada. O mock reproduzia um estado que a produção
jamais atingia — então o conserto inteiro era inerte ponta a ponta e a suíte dizia
que estava verde. Um scan em que NENHUM scanner rodou chegava à tela assim:

    state: "done"   errors: []   coverage_complete: true   findings: 0

que é indistinguível de um alvo limpo.

A regra que sai daqui: **teste de cobertura afirma sobre o dado PERSISTIDO.** Mock de
estrutura prova serialização; só o que a produção grava prova comportamento.
"""

from __future__ import annotations

import uuid

import pytest

from orchestrator.config import settings
from orchestrator.domain.schemas import AssetType, ScanHandle, ScanStatus, Target
from orchestrator.jobs.pipelines import run_scan
from orchestrator.persistence.db import init_db, session
from orchestrator.persistence.models import ScanRow, ScanState


class _SemBinario:
    """Adapter cujo binário não existe — o caso do trivy sem a imagem certa."""

    name = "trivy"

    async def health(self) -> bool:
        return False


class _QueAcha:
    """Adapter que roda e acha — para o caso de cobertura PARCIAL."""

    name = "gitleaks"

    async def health(self) -> bool:
        return True

    async def start_scan(self, target, options):
        return ScanHandle(adapter=self.name, native_id="1", metadata={})

    async def poll(self, handle):
        return ScanStatus.DONE

    async def fetch_results(self, handle):
        from orchestrator.domain.schemas import RawResults

        return RawResults(adapter=self.name, payload=[])

    async def normalize(self, raw):
        from orchestrator.domain.schemas import Confidence, Evidence, Finding, Severity

        return [
            Finding(
                scan_id=uuid.uuid4(),
                target=Target(asset_type=AssetType.REPO, value="x.py:1"),
                source_tool=self.name,
                source_rule_id="regra-de-teste",
                title="segredo de teste",
                description="d",
                severity=Severity.HIGH,
                confidence=Confidence.FIRM,
                evidence=[Evidence(description="e")],
            )
        ]


@pytest.fixture(autouse=True)
async def _db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Banco NOVO por teste.

    O SQLite de dev do repo tem o schema antigo, e `create_all` não faz ALTER — em
    produção quem migra é o alembic. Um engine próprio garante que o teste afirme
    sobre o schema atual, e não sobre um arquivo esquecido na máquina.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession

    from orchestrator.persistence import db as dbmod

    monkeypatch.setattr(settings, "LAB_ONLY", False)
    monkeypatch.setattr(settings, "REPORTS_DIR", tmp_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cobertura.db'}")
    monkeypatch.setattr(dbmod, "_engine", engine)
    monkeypatch.setattr(
        dbmod,
        "_session_factory",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
    )
    await init_db()
    yield
    await engine.dispose()


async def _linha(scan_id: uuid.UUID) -> ScanRow:
    async with session() as s:
        row = await s.get(ScanRow, scan_id)
    assert row is not None, "o scan nem foi persistido"
    return row


async def test_scanner_que_nao_rodou_chega_na_linha_do_scan() -> None:
    """O elo que faltava: `scanners_skipped` gravado, não só calculado."""
    sid = uuid.uuid4()
    r = await run_scan(
        Target(asset_type=AssetType.IMAGE, value="alpine:3.19"),
        adapters=[_SemBinario()],
        skip_ai=True,
        scan_id=sid,
    )
    assert not r.coverage_is_complete

    row = await _linha(sid)
    assert row.scanners_skipped, "cobertura incompleta morreu no worker"
    assert "trivy" in row.scanners_skipped
    assert row.errors, "`errors` continua sem ser gravado"
    assert any("trivy" in e for e in row.errors)


async def test_scan_em_que_nada_rodou_nao_termina_verde() -> None:
    """`state=done` com zero achados é lido como alvo limpo. Nada rodou = falhou."""
    sid = uuid.uuid4()
    await run_scan(
        Target(asset_type=AssetType.IMAGE, value="alpine:3.19"),
        adapters=[_SemBinario()],
        skip_ai=True,
        scan_id=sid,
    )
    row = await _linha(sid)
    assert row.state == ScanState.FAILED.value, (
        f"scan sem nenhum scanner executado terminou '{row.state}' — verde é a cor "
        "de 'imagem sem CVE'"
    )


async def test_cobertura_parcial_continua_done_mas_declara_a_lacuna() -> None:
    """Houve verificação real: não é falha. Mas a lacuna não pode sumir."""
    sid = uuid.uuid4()
    await run_scan(
        Target(asset_type=AssetType.REPO, value="https://example.test/r.git"),
        adapters=[_QueAcha(), _SemBinario()],
        skip_ai=True,
        scan_id=sid,
    )
    row = await _linha(sid)
    assert row.state == ScanState.DONE.value
    assert row.scanners_ran == ["gitleaks"]
    assert "trivy" in row.scanners_skipped


async def test_scan_completo_nao_inventa_lacuna() -> None:
    sid = uuid.uuid4()
    await run_scan(
        Target(asset_type=AssetType.REPO, value="https://example.test/r.git"),
        adapters=[_QueAcha()],
        skip_ai=True,
        scan_id=sid,
    )
    row = await _linha(sid)
    assert row.state == ScanState.DONE.value
    assert row.scanners_skipped == {}
    assert row.scanners_ran == ["gitleaks"]


async def test_report_path_persistido_para_o_relatorio_ser_baixavel() -> None:
    """`GET /reports/{id}` devolvia 404 SEMPRE: `report_path` nunca era gravado.

    O relatório técnico é o ÚNICO artefato que renderiza `errors` — ficava num
    arquivo em disco que rota nenhuma servia.
    """
    from pathlib import Path

    sid = uuid.uuid4()
    await run_scan(
        Target(asset_type=AssetType.REPO, value="https://example.test/r.git"),
        adapters=[_QueAcha()],
        skip_ai=True,
        scan_id=sid,
    )
    row = await _linha(sid)
    assert row.report_path, "report_path não foi gravado — o download dá 404"
    assert Path(row.report_path).exists()


async def test_bundle_le_a_cobertura_da_linha_persistida() -> None:
    """Ponta a ponta: o que a IA de patch recebe reflete o que de fato rodou."""
    from orchestrator.reporting.exporters.ai_bundle import _coverage

    sid = uuid.uuid4()
    await run_scan(
        Target(asset_type=AssetType.IMAGE, value="alpine:3.19"),
        adapters=[_SemBinario()],
        skip_ai=True,
        scan_id=sid,
    )
    cov = _coverage(await _linha(sid))
    assert cov["coverage_complete"] is False
    assert cov["scanners_executed"] == []
    assert cov["scanners_failed"] == ["trivy"]
    assert cov["coverage_state"] == "incompleta"
    assert "NENHUM scanner foi executado" in cov["coverage_note"]


# ============================================ o executivo, que vai para auditoria


def test_executivo_mostra_cobertura_incompleta_antes_da_nota(tmp_path) -> None:
    """O documento de maior consequência era o único que não sabia dizer isso.

    `render_executive` não recebia `errors` e o template não tinha bloco de
    cobertura: um scan em que NADA rodou saía com "nota A, índice 0/100, zero
    achados" e mapeamento OWASP/PCI/LGPD todo zerado, sem uma linha de aviso.
    """
    from pathlib import Path

    from orchestrator.jobs.pipelines import ScanResult
    from orchestrator.reporting.renderer import render_executive

    r = ScanResult(
        scan_id=uuid.uuid4(),
        target=Target(asset_type=AssetType.IMAGE, value="alpine:3.19"),
    )
    r.scanners_skipped["trivy"] = "binário ausente"
    saida = render_executive(r, Path(tmp_path) / "exec.html")
    html = saida.read_text(encoding="utf-8")

    assert "Cobertura incompleta" in html
    assert "NENHUM scanner foi executado" in html
    assert "trivy" in html and "binário ausente" in html
    # e a nota continua lá — o aviso não some com ela, aparece ANTES
    assert html.index("Cobertura incompleta") < html.index("Sumário Executivo")


def test_executivo_completo_nao_alarma_a_toa(tmp_path) -> None:
    from pathlib import Path

    from orchestrator.jobs.pipelines import ScanResult
    from orchestrator.reporting.renderer import render_executive

    r = ScanResult(scan_id=uuid.uuid4(), target=Target(asset_type=AssetType.IMAGE, value="alpine"))
    r.scanners_ran.append("trivy")
    html = render_executive(r, Path(tmp_path) / "e.html").read_text(encoding="utf-8")
    assert "Cobertura incompleta" not in html
    assert "Cobertura completa" in html


# ================================================= OSINT declara o que não rodou


async def test_exposure_declara_vetor_que_nao_rodou() -> None:
    """Onze saídas de falha escreviam só em `errors`; `scanners_skipped` ficava vazio.

    Na configuração de estreia (sem token, sem chave, sem binário) o relatório de
    exposição saía com `coverage_is_complete = True` tendo consultado NADA.
    """
    from orchestrator.jobs.exposure import run_exposure_scan

    r = await run_exposure_scan(
        company_name="Banco Teste",
        domains=["banco.test"],
        github_orgs=[],
        dorks=["banco password"],
        skip_ai=True,
    )
    assert not r.coverage_is_complete, "OSINT sem nenhuma credencial não é cobertura completa"
    assert "shodan" in r.scanners_skipped
    assert "subdomain_takeover" in r.scanners_skipped
    for motivo in r.scanners_skipped.values():
        assert motivo.strip(), "vetor pulado sem motivo escrito"


# ======================================== health() nunca levanta (contrato do base)


@pytest.mark.parametrize(
    "fabrica",
    [
        "orchestrator.adapters.github_exposure_adapter:GitHubExposureAdapter",
        "orchestrator.adapters.shodan_adapter:ShodanAdapter",
        "orchestrator.adapters.censys_adapter:CensysAdapter",
        "orchestrator.adapters.nmap_adapter:NmapAdapter",
        "orchestrator.adapters.trivy_adapter:TrivyAdapter",
        "orchestrator.adapters.semgrep_adapter:SemgrepAdapter",
        "orchestrator.adapters.checkov_adapter:CheckovAdapter",
        "orchestrator.adapters.gitleaks_adapter:GitleaksAdapter",
        "orchestrator.adapters.trufflehog_adapter:TrufflehogAdapter",
        "orchestrator.adapters.dnstwist_adapter:DnstwistAdapter",
        "orchestrator.adapters.kube_bench_adapter:KubeBenchAdapter",
        "orchestrator.adapters.nuclei_adapter:NucleiAdapter",
        "orchestrator.adapters.subdomain_takeover_adapter:SubdomainTakeoverAdapter",
        "orchestrator.adapters.zap_adapter:ZAPAdapter",
        "orchestrator.adapters.greenbone_adapter:GreenboneAdapter",
    ],
)
async def test_health_devolve_bool_e_nunca_levanta(fabrica: str, monkeypatch) -> None:
    """Contrato do `ScannerAdapter`: health() SEMPRE devolve bool.

    Não é preciosismo. O `github_exposure` levantava `SSLError` (o except pegava só
    `GithubException` e `RuntimeError`), e no `run_exposure_scan` a chamada não está
    dentro de try — o pipeline OSINT inteiro morria por causa de um erro de rede.
    """
    import importlib

    mod_nome, cls_nome = fabrica.split(":")
    cls = getattr(importlib.import_module(mod_nome), cls_nome)
    # PATH vazio: nenhum binário resolve, e as chamadas de rede saem sem credencial.
    monkeypatch.setenv("PATH", "/nao/existe")
    # ZAP exige base_url; os outros constroem sem argumento.
    ad = cls(base_url="http://127.0.0.1:1") if cls_nome == "ZAPAdapter" else cls()
    resultado = await ad.health()
    assert isinstance(resultado, bool)
    fechar = getattr(ad, "aclose", None)
    if fechar:
        await fechar()


# ===================================== o painel de saúde não pode mentir também


async def test_health_full_nao_diz_ok_para_chave_de_nuvem_nao_testada() -> None:
    """Chave CONFIGURADA não é chave que funciona.

    Antes, chave revogada, expirada ou com cota estourada aparecia como `ok`,
    idêntica a uma boa. É o defeito do `health()` do censys no painel do operador.
    """
    from orchestrator.api.routers.health import _check_llm_cloud
    from orchestrator.config import settings

    original = settings.ANTHROPIC_API_KEY
    try:
        settings.ANTHROPIC_API_KEY = "chave-que-pode-estar-revogada"
        r = await _check_llm_cloud()
        assert r["status"] == "configured", "'ok' afirma o que não foi verificado"
        assert "NÃO verificada" in r["detail"]["note"]
    finally:
        settings.ANTHROPIC_API_KEY = original


async def test_health_full_reporta_scanner_ausente(monkeypatch) -> None:
    """O painel checava Postgres/Redis/ZAP/LLM e NENHUM scanner.

    Ficava todo verde numa imagem sem nmap, sem trivy, sem semgrep — exatamente o
    estado em que todo scan fecha com zero achados.
    """
    from orchestrator.api.routers.health import _check_scanners

    monkeypatch.setenv("PATH", "/nao/existe")
    r = await _check_scanners()
    assert r["status"] == "degraded"
    assert "nmap" in r["detail"]["ausentes"]
    assert "sem verificação" in r["detail"]["note"]


# ============================== "não tenho o dado" != "tudo rodou" (fonte única)


def test_cobertura_desconhecida_nao_vira_completa() -> None:
    """`pulados` vazio significa DUAS coisas opostas.

    "Nada foi pulado" e "não tenho o dado". O bundle aprendeu a distinguir; o
    executivo continuou tratando as duas como "tudo rodou" — a mesma mentira, mais
    discreta. Agora a conta mora em UM lugar (`reporting/coverage.py`) e as três
    superfícies leem de lá.

    Caminhos reais que produzem o estado desconhecido: scan ainda em andamento, o
    `_persist_findings` (best-effort) falhando com o DB fora, e toda linha anterior à
    migration 0007.
    """
    from types import SimpleNamespace

    from orchestrator.reporting.coverage import resumo

    c = resumo(SimpleNamespace(requested_scanners=["nmap", "zap"]))
    assert c["estado"] == "desconhecida"
    assert c["completa"] is False
    assert "DESCONHECIDA" in c["nota"]


def test_executivo_sem_dado_de_cobertura_avisa(tmp_path) -> None:
    from pathlib import Path

    from orchestrator.jobs.pipelines import ScanResult
    from orchestrator.reporting.renderer import render_executive

    r = ScanResult(
        scan_id=uuid.uuid4(), target=Target(asset_type=AssetType.HOST, value="10.0.0.1")
    )  # nada rodou, nada pulado: o pipeline não registrou
    html = render_executive(r, Path(tmp_path) / "e.html").read_text(encoding="utf-8")
    assert "Cobertura desconhecida" in html
    assert html.index("Cobertura desconhecida") < html.index("Sumário Executivo")


def test_as_tres_superficies_concordam() -> None:
    """Bundle, executivo e UI leem a MESMA função. Divergir de novo exige mudá-la."""
    import inspect

    from orchestrator.api.routers import ui
    from orchestrator.reporting import renderer
    from orchestrator.reporting.exporters import ai_bundle

    for mod in (ai_bundle, renderer, ui):
        fonte = inspect.getsource(mod)
        assert "reporting.coverage import resumo" in fonte, (
            f"{mod.__name__} calcula cobertura por conta própria — é assim que as "
            "telas voltam a discordar"
        )


# ============================ o OSINT também tem que chegar ao banco e à tela


async def test_exposure_persiste_findings_e_cobertura() -> None:
    """`run_exposure_scan` não tinha UMA referência a `session`/`ScanRow`.

    Renderizava o HTML e dava `return result`; o `POST /exposure/scan` devolve só um
    `job_id`. Findings, cobertura e `report_path` do OSINT nunca chegavam ao banco,
    à API, à fila de findings nem ao executivo — o `scanners_skipped` que este job
    passou a preencher morria no worker. O mesmo defeito do `run_scan`, intacto uma
    camada ao lado.
    """
    from orchestrator.jobs.exposure import run_exposure_scan

    r = await run_exposure_scan(
        company_name="Banco Teste Persistencia",
        domains=["banco.test"],
        github_orgs=[],
        dorks=["banco password"],
        skip_ai=True,
    )
    row = await _linha(r.scan_id)
    assert row.scanners_skipped, "cobertura do OSINT não chegou ao banco"
    assert "shodan" in row.scanners_skipped
    assert row.report_path, "o relatório de exposição não é recuperável pela API"
    assert row.state in ("done", "failed")
