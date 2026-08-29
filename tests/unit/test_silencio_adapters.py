"""A varredura do silêncio: zero achados só pode significar "verifiquei e não achei".

Este arquivo é a catraca de um defeito que já apareceu em nove adapters diferentes,
sempre com a mesma forma: a ferramenta não roda (binário ausente, credencial
inválida, rate limit, cluster inalcançável, saída truncada), o erro vira `[]`, `{}`
ou um dicionário fabricado, e o relatório apresenta isso como alvo limpo.

A regra que cada teste aqui defende: **falha de execução vira `ScanIntegrityError`
(cobertura declarada como incompleta); perda parcial vira `coverage_gaps`, que o
pipeline transforma em achado INFO visível.** Nunca um zero silencioso.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from orchestrator.adapters.base import (
    ScanIntegrityError,
    coverage_gap_finding,
    read_jsonl,
)
from orchestrator.domain.schemas import (
    AssetType,
    ScanHandle,
    ScanStatus,
    Severity,
    Target,
)


def _falsa() -> str:
    """Credencial de teste gerada em tempo de execução.

    Literal aqui reprovaria no `ruff S106` e pediria uma linha na allowlist do
    gitleaks — e allowlist de scanner de segredo é onde segredo de verdade se
    esconde. Gerar resolve os dois sem afrouxar gate nenhum.
    """
    return secrets.token_hex(4)


def _h(nome: str, nid: str) -> ScanHandle:
    return ScanHandle(adapter=nome, native_id=nid, metadata={})


# ============================================================== helper JSONL


def test_jsonl_com_tudo_ilegivel_reprova(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    p.write_text("{quebrado\n{tambem quebrado\n", encoding="utf-8")
    with pytest.raises(ScanIntegrityError, match="ilegíveis"):
        read_jsonl(p, adapter="nuclei", gaps=[])


def test_jsonl_com_perda_parcial_preserva_e_declara(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    p.write_text('{"a": 1}\n{quebrado\n{"b": 2}\n', encoding="utf-8")
    gaps: list[str] = []
    itens = read_jsonl(p, adapter="nuclei", gaps=gaps)
    assert len(itens) == 2, "não pode jogar fora achado bom"
    assert gaps and "1 linha(s)" in gaps[0], "não pode jogar fora a linha ruim em silêncio"


def test_jsonl_limpo_nao_inventa_lacuna(tmp_path: Path) -> None:
    p = tmp_path / "out.jsonl"
    p.write_text('{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")
    gaps: list[str] = []
    assert len(read_jsonl(p, adapter="nuclei", gaps=gaps)) == 2
    assert gaps == []


def test_arquivo_ausente_e_zero_legitimo(tmp_path: Path) -> None:
    """Ausência de arquivo é tratada por quem chama (o adapter sabe se era esperado)."""
    gaps: list[str] = []
    assert read_jsonl(tmp_path / "nao_existe.jsonl", adapter="nuclei", gaps=gaps) == []
    assert gaps == []


def test_achado_de_lacuna_e_visivel_e_info() -> None:
    f = coverage_gap_finding(
        adapter="nuclei",
        gaps=["3 linha(s) descartadas"],
        scan_id=uuid4(),
        target=Target(asset_type=AssetType.URL, value="https://app.test"),
    )
    assert f.severity == Severity.INFO
    assert "sem verificação" in f.description
    assert "3 linha(s)" in f.description


# ================================================================== gitleaks


@pytest.mark.asyncio
async def test_gitleaks_sem_report_nao_e_repo_limpo(tmp_path: Path) -> None:
    """Clone que falha não pode virar "0 segredos"."""
    from orchestrator.adapters.gitleaks_adapter import GitleaksAdapter

    ad = GitleaksAdapter()
    nid = str(uuid4())
    faltando = tmp_path / "report.json"

    async def _t() -> tuple[int, Path]:
        return 0, faltando

    ad._tasks[nid] = asyncio.get_event_loop().create_task(_t())
    await asyncio.sleep(0)
    with pytest.raises(ScanIntegrityError, match="n.o rodou"):
        await ad.fetch_results(_h("gitleaks", nid))


@pytest.mark.asyncio
async def test_gitleaks_report_corrompido_reprova(tmp_path: Path) -> None:
    from orchestrator.adapters.gitleaks_adapter import GitleaksAdapter

    ad = GitleaksAdapter()
    nid = str(uuid4())
    p = tmp_path / "report.json"
    p.write_text("[{ truncado", encoding="utf-8")

    async def _t() -> tuple[int, Path]:
        return 0, p

    ad._tasks[nid] = asyncio.get_event_loop().create_task(_t())
    await asyncio.sleep(0)
    with pytest.raises(ScanIntegrityError, match="n.o . JSON"):
        await ad.fetch_results(_h("gitleaks", nid))


@pytest.mark.asyncio
async def test_gitleaks_array_vazio_e_limpo_de_verdade(tmp_path: Path) -> None:
    """O caso honesto tem que continuar passando — senão o gate vira ruído."""
    from orchestrator.adapters.gitleaks_adapter import GitleaksAdapter

    ad = GitleaksAdapter()
    nid = str(uuid4())
    p = tmp_path / "report.json"
    p.write_text("[]", encoding="utf-8")

    async def _t() -> tuple[int, Path]:
        return 0, p

    ad._tasks[nid] = asyncio.get_event_loop().create_task(_t())
    await asyncio.sleep(0)
    raw = await ad.fetch_results(_h("gitleaks", nid))
    assert raw.payload == []
    assert await ad.normalize(raw) == []


# ================================================================ kube_bench


@pytest.mark.asyncio
async def test_kube_bench_saida_vazia_nao_e_conformidade(tmp_path: Path) -> None:
    from orchestrator.adapters.kube_bench_adapter import KubeBenchAdapter

    ad = KubeBenchAdapter()
    nid = str(uuid4())
    p = tmp_path / "out.json"
    p.write_text("", encoding="utf-8")
    ad._outs[nid] = p
    with pytest.raises(ScanIntegrityError, match="vazia"):
        await ad.fetch_results(_h("kube_bench", nid))


@pytest.mark.asyncio
async def test_kube_bench_zero_controles_avaliados_reprova(tmp_path: Path) -> None:
    from orchestrator.adapters.kube_bench_adapter import KubeBenchAdapter

    ad = KubeBenchAdapter()
    nid = str(uuid4())
    p = tmp_path / "out.json"
    p.write_text(json.dumps({"Controls": []}), encoding="utf-8")
    ad._outs[nid] = p
    with pytest.raises(ScanIntegrityError, match="NENHUM controle"):
        await ad.fetch_results(_h("kube_bench", nid))


@pytest.mark.asyncio
async def test_kube_bench_cluster_conforme_passa(tmp_path: Path) -> None:
    """Controles avaliados e todos PASS: zero achados aqui é verdade."""
    from orchestrator.adapters.kube_bench_adapter import KubeBenchAdapter

    ad = KubeBenchAdapter()
    nid = str(uuid4())
    p = tmp_path / "out.json"
    p.write_text(
        json.dumps(
            {"Controls": [{"tests": [{"results": [{"status": "PASS", "test_number": "1.1.1"}]}]}]}
        ),
        encoding="utf-8",
    )
    ad._outs[nid] = p
    raw = await ad.fetch_results(_h("kube_bench", nid))
    assert await ad.normalize(raw) == []


@pytest.mark.asyncio
async def test_kube_bench_poll_reprova_com_rc_nao_zero() -> None:
    from orchestrator.adapters.kube_bench_adapter import KubeBenchAdapter

    ad = KubeBenchAdapter()
    nid = str(uuid4())

    async def _t() -> int:
        return 1

    ad._tasks[nid] = asyncio.get_event_loop().create_task(_t())
    await asyncio.sleep(0)
    assert await ad.poll(_h("kube_bench", nid)) == ScanStatus.FAILED


# ==================================================================== shodan


@pytest.mark.asyncio
async def test_shodan_falha_de_busca_nao_vira_zero_exposicoes(monkeypatch) -> None:
    """O adapter FABRICAVA {"matches": [], "total": 0} em qualquer exceção."""
    from orchestrator.adapters import shodan_adapter as mod

    class _FakeApi:
        def __init__(self, *a, **k) -> None: ...

        def search(self, *a, **k):
            raise RuntimeError("API rate limit reached")

    monkeypatch.setitem(__import__("sys").modules, "shodan", type("M", (), {"Shodan": _FakeApi}))
    ad = mod.ShodanAdapter(api_key=_falsa())
    with pytest.raises(ScanIntegrityError, match="inven..o"):
        await ad.start_scan(Target(asset_type=AssetType.HOST, value="org:Banco"), {})


@pytest.mark.asyncio
async def test_shodan_pagina_parcial_declara_lacuna(monkeypatch) -> None:
    from orchestrator.adapters import shodan_adapter as mod

    class _FakeApi:
        def __init__(self, *a, **k) -> None: ...

        def search(self, *a, **k):
            return {"total": 4200, "matches": [{"ip_str": "1.2.3.4", "port": 443}]}

    monkeypatch.setitem(__import__("sys").modules, "shodan", type("M", (), {"Shodan": _FakeApi}))
    ad = mod.ShodanAdapter(api_key=_falsa())
    h = await ad.start_scan(Target(asset_type=AssetType.HOST, value="org:Banco"), {})
    raw = await ad.fetch_results(h)
    assert raw.coverage_gaps, "4200 resultados e 1 lido não pode passar como completo"
    assert "4200" in raw.coverage_gaps[0]


# ==================================================================== censys


@pytest.mark.asyncio
async def test_censys_erro_sem_resultado_reprova(monkeypatch) -> None:
    from orchestrator.adapters import censys_adapter as mod

    class _Hosts:
        def __init__(self, *a, **k) -> None: ...

        def search(self, *a, **k):
            raise RuntimeError("401 unauthorized")

    monkeypatch.setitem(
        __import__("sys").modules,
        "censys.search",
        type("M", (), {"CensysHosts": _Hosts}),
    )
    ad = mod.CensysAdapter(api_id=_falsa(), api_secret=_falsa())
    with pytest.raises(ScanIntegrityError, match="inven..o"):
        await ad.start_scan(Target(asset_type=AssetType.HOST, value="banco"), {})


@pytest.mark.asyncio
async def test_censys_paginacao_interrompida_declara_lacuna(monkeypatch) -> None:
    """Uma página lida de três pedidas não é resultado completo."""
    from orchestrator.adapters import censys_adapter as mod

    class _Hosts:
        def __init__(self, *a, **k) -> None: ...

        def search(self, *a, **k):
            def _gen():
                yield [{"ip": "1.1.1.1", "services": []}]
                raise RuntimeError("timeout na pagina 2")

            return _gen()

    monkeypatch.setitem(
        __import__("sys").modules,
        "censys.search",
        type("M", (), {"CensysHosts": _Hosts}),
    )
    ad = mod.CensysAdapter(api_id=_falsa(), api_secret=_falsa())
    h = await ad.start_scan(Target(asset_type=AssetType.HOST, value="banco"), {"pages": 3})
    raw = await ad.fetch_results(h)
    assert raw.coverage_gaps and "1 de 3" in raw.coverage_gaps[0]


# =========================================================== github_exposure


@pytest.mark.asyncio
async def test_github_rate_limit_declara_dorks_nao_consultadas(monkeypatch) -> None:
    """Antes: `break` silencioso — 3 dorks de 10 viravam "o resultado das 10"."""
    from github.GithubException import RateLimitExceededException

    from orchestrator.adapters import github_exposure_adapter as mod

    class _Gh:
        def search_code(self, dork):
            if dork in ("d1", "d2"):
                return []
            raise RateLimitExceededException(403, "rate limit", {})

    ad = mod.GitHubExposureAdapter(token=_falsa())
    monkeypatch.setattr(ad, "_gh", lambda: _Gh())
    dorks = [f"d{i}" for i in range(1, 11)]
    h = await ad.start_scan(Target(asset_type=AssetType.REPO, value="banco"), {"dorks": dorks})
    raw = await ad.fetch_results(h)
    assert raw.coverage_gaps, "rate limit tem que aparecer no relatório"
    assert "8 de 10" in raw.coverage_gaps[0]


@pytest.mark.asyncio
async def test_github_rate_limit_na_primeira_dork_reprova(monkeypatch) -> None:
    from github.GithubException import RateLimitExceededException

    from orchestrator.adapters import github_exposure_adapter as mod

    class _Gh:
        def search_code(self, dork):
            raise RateLimitExceededException(403, "rate limit", {})

    ad = mod.GitHubExposureAdapter(token=_falsa())
    monkeypatch.setattr(ad, "_gh", lambda: _Gh())
    with pytest.raises(ScanIntegrityError, match="nenhuma das"):
        await ad.start_scan(Target(asset_type=AssetType.REPO, value="banco"), {"dorks": ["a", "b"]})


# ======================================================================= zap


@pytest.mark.asyncio
async def test_zap_sem_url_rastreada_nao_e_app_segura() -> None:
    """Fila passiva vazia + zero URLs = nada foi verificado."""
    from orchestrator.adapters.zap_adapter import ZAPAdapter

    ad = ZAPAdapter(base_url="http://zap:8090", api_key=_falsa())
    nid = str(uuid4())
    ad._scans[nid] = {"url": "https://app.test", "phase": "done", "urls_rastreadas": 0}
    with pytest.raises(ScanIntegrityError, match="NENHUMA URL"):
        await ad.fetch_results(_h("zap", nid))
    await ad.aclose()


@pytest.mark.asyncio
async def test_zap_pagina_todos_os_alertas() -> None:
    """Antes: uma única página de 500. Alerta 501 sumia do relatório."""
    from orchestrator.adapters.zap_adapter import ZAPAdapter

    ad = ZAPAdapter(base_url="http://zap:8090", api_key=_falsa())
    nid = str(uuid4())
    ad._scans[nid] = {"url": "https://app.test", "phase": "done", "urls_rastreadas": 42}

    paginas = [
        {"alerts": [{"name": f"a{i}"} for i in range(500)]},
        {"alerts": [{"name": f"b{i}"} for i in range(120)]},
    ]
    chamadas: list[dict] = []

    async def _fake(path: str, **params):
        if path == "/JSON/core/view/alerts/":
            chamadas.append(params)
            return paginas[len(chamadas) - 1]
        if path == "/JSON/alert/view/alertCountsByRisk/":
            return {"High": "620"}
        return {}

    ad._get = _fake  # type: ignore[assignment]
    raw = await ad.fetch_results(_h("zap", nid))
    assert len(raw.payload["alerts"]) == 620, "o excedente da primeira página sumiu"
    assert [c["start"] for c in chamadas] == ["0", "500"]
    await ad.aclose()


@pytest.mark.asyncio
async def test_zap_alerta_fora_do_prefixo_vira_lacuna() -> None:
    """`baseurl` filtra por prefixo: redirect para outro host esconde alertas."""
    from orchestrator.adapters.zap_adapter import ZAPAdapter

    ad = ZAPAdapter(base_url="http://zap:8090", api_key=_falsa())
    nid = str(uuid4())
    ad._scans[nid] = {"url": "http://app.test", "phase": "done", "urls_rastreadas": 9}

    async def _fake(path: str, **params):
        if path == "/JSON/core/view/alerts/":
            return {"alerts": [{"name": "x"}]}
        if path == "/JSON/alert/view/alertCountsByRisk/":
            return {"High": "5", "Low": "3"}  # 8 na sessão, 1 sob o prefixo
        return {}

    ad._get = _fake  # type: ignore[assignment]
    raw = await ad.fetch_results(_h("zap", nid))
    assert raw.coverage_gaps and "8 alerta(s)" in raw.coverage_gaps[0]
    await ad.aclose()


@pytest.mark.asyncio
async def test_zap_conta_urls_antes_de_fechar() -> None:
    """poll não pode declarar DONE sem medir se houve rastreamento."""
    from orchestrator.adapters.zap_adapter import ZAPAdapter

    ad = ZAPAdapter(base_url="http://zap:8090", api_key=_falsa())
    nid = str(uuid4())
    ad._scans[nid] = {"url": "https://app.test", "phase": "passive_wait", "active": False}
    ad._get = AsyncMock(
        side_effect=lambda path, **p: (
            {"recordsToScan": "0"} if "pscan" in path else {"urls": ["u1", "u2"]}
        )
    )
    assert await ad.poll(_h("zap", nid)) == ScanStatus.DONE
    assert ad._scans[nid]["urls_rastreadas"] == 2
    await ad.aclose()


# ====================================================== subdomain_takeover


@pytest.mark.asyncio
async def test_subtake_etapa_que_falha_reprova(tmp_path: Path) -> None:
    """Cascata silenciosa: subfinder morria e as outras duas nem eram chamadas."""
    from orchestrator.adapters.subdomain_takeover_adapter import (
        SubdomainTakeoverAdapter,
    )

    ad = SubdomainTakeoverAdapter()
    nid = str(uuid4())
    out = tmp_path / "out.jsonl"

    async def _t() -> tuple[int, Path]:
        return 1, out

    ad._tasks[nid] = asyncio.get_event_loop().create_task(_t())
    await asyncio.sleep(0)
    assert await ad.poll(_h("subdomain_takeover", nid)) == ScanStatus.FAILED
    with pytest.raises(ScanIntegrityError, match="tr.s "):
        await ad.fetch_results(_h("subdomain_takeover", nid))


@pytest.mark.asyncio
async def test_subtake_sem_saida_nao_e_dominio_seguro(tmp_path: Path) -> None:
    from orchestrator.adapters.subdomain_takeover_adapter import (
        SubdomainTakeoverAdapter,
    )

    ad = SubdomainTakeoverAdapter()
    nid = str(uuid4())

    async def _t() -> tuple[int, Path]:
        return 0, tmp_path / "nao_existe.jsonl"

    ad._tasks[nid] = asyncio.get_event_loop().create_task(_t())
    await asyncio.sleep(0)
    with pytest.raises(ScanIntegrityError, match="n.o produziu sa.da"):
        await ad.fetch_results(_h("subdomain_takeover", nid))


@pytest.mark.asyncio
async def test_subtake_zero_achados_com_pipeline_ok_e_limpo(tmp_path: Path) -> None:
    from orchestrator.adapters.subdomain_takeover_adapter import (
        SubdomainTakeoverAdapter,
    )

    ad = SubdomainTakeoverAdapter()
    nid = str(uuid4())
    out = tmp_path / "out.jsonl"
    out.touch()

    async def _t() -> tuple[int, Path]:
        return 0, out

    ad._tasks[nid] = asyncio.get_event_loop().create_task(_t())
    await asyncio.sleep(0)
    raw = await ad.fetch_results(_h("subdomain_takeover", nid))
    assert raw.payload == []
    assert raw.coverage_gaps == []


def test_subtake_usa_duc_e_ni_no_nuclei() -> None:
    """Regressão nominal: o nuclei sem -duc/-ni pendura até o timeout num banco."""
    fonte = Path("orchestrator/adapters/subdomain_takeover_adapter.py").read_text(encoding="utf-8")
    assert '"-duc"' in fonte and '"-ni"' in fonte


# ============================================ o mecanismo, no pipeline inteiro


@pytest.mark.asyncio
async def test_pipeline_transforma_lacuna_em_achado_visivel() -> None:
    """O elo que fecha a regra: `coverage_gaps` do adapter vira achado no relatório.

    Sem isto, cada `normalize()` teria que lembrar de emitir o aviso — quinze
    adapters lembrando é convenção, e convenção não é mecanismo.
    """
    from orchestrator.domain.schemas import Finding, RawResults
    from orchestrator.jobs.pipelines import _run_adapter

    class _Fake:
        name = "fake"

        async def health(self) -> bool:
            return True

        async def start_scan(self, target, options):
            return ScanHandle(adapter=self.name, native_id="1", metadata={})

        async def poll(self, handle):
            return ScanStatus.DONE

        async def fetch_results(self, handle):
            return RawResults(
                adapter=self.name,
                payload=[],
                coverage_gaps=["2 dork(s) não foram consultadas"],
            )

        async def normalize(self, raw) -> list[Finding]:
            return []

    alvo = Target(asset_type=AssetType.URL, value="https://app.test")
    achados = await _run_adapter(_Fake(), alvo, {}, poll_every=0.0)
    assert len(achados) == 1, "a lacuna sumiu do resultado"
    assert achados[0].severity == Severity.INFO
    assert achados[0].source_rule_id == "fake-coverage-gap"
    assert "não foram consultadas" in achados[0].description


@pytest.mark.asyncio
async def test_pipeline_nao_inventa_achado_quando_nao_ha_lacuna() -> None:
    from orchestrator.domain.schemas import Finding, RawResults
    from orchestrator.jobs.pipelines import _run_adapter

    class _Fake:
        name = "fake"

        async def health(self) -> bool:
            return True

        async def start_scan(self, target, options):
            return ScanHandle(adapter=self.name, native_id="1", metadata={})

        async def poll(self, handle):
            return ScanStatus.DONE

        async def fetch_results(self, handle):
            return RawResults(adapter=self.name, payload=[])

        async def normalize(self, raw) -> list[Finding]:
            return []

    alvo = Target(asset_type=AssetType.URL, value="https://app.test")
    assert await _run_adapter(_Fake(), alvo, {}, poll_every=0.0) == []
