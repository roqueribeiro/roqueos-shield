"""W2: os gates, os perfis, a trilha de auditoria e a ordem que a API prometia e não cumpria.

Um teste por conserto, cada um com a mutação que o reprova anotada no topo do teste
(reverter o conserto faz o teste falhar; conferido ao escrever).
"""

from __future__ import annotations

import inspect
import random
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select
from typer.testing import CliRunner

from orchestrator import cli as cai_cli
from orchestrator.api import deps
from orchestrator.api.routers import exposure as exposure_router
from orchestrator.api.routers import scans as scans_router
from orchestrator.api.routers.scans import (
    GateRecusado,
    gates_do_scan,
    perfil_do_scan,
    scanners_do_scan,
)
from orchestrator.cliente import cli as cliente_cli
from orchestrator.cliente.mcp_nucleo import FERRAMENTAS_DE_ACAO
from orchestrator.config import Settings, settings
from orchestrator.domain import target_validator as tv
from orchestrator.domain.dedup import heuristic_dedup
from orchestrator.domain.roles import Role
from orchestrator.domain.schemas import (
    AssetType,
    Confidence,
    Finding,
    RawResults,
    ScanHandle,
    ScanStatus,
    Severity,
    Target,
)
from orchestrator.jobs import pipelines
from orchestrator.jobs.pipelines import (
    PERFIS_DO_SCAN,
    SCANNERS_EXPOSURE,
    SEM_SCANNER,
    resolve_scanners,
    resolve_scanners_com_motivo,
)
from orchestrator.main import app
from orchestrator.persistence.db import init_db, session
from orchestrator.persistence.models import AuditLogRow, ScanRow, TargetRow

RAIZ = Path(__file__).resolve().parents[2]


@pytest_asyncio.fixture(autouse=True)
async def _banco() -> Any:
    await init_db()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def escopo_aberto(monkeypatch: pytest.MonkeyPatch) -> None:
    """Alvo público que resolve, sem LAB_ONLY: só o gate de autorização decide."""
    monkeypatch.setattr(settings, "LAB_ONLY", False)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    monkeypatch.setattr(settings, "REQUIRE_AUTH_REF", False)
    monkeypatch.setattr(tv, "_resolve_host_ips", lambda h: ["8.8.8.8"])


@pytest.fixture
def sem_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """`aplicar` leria a tabela app_settings (que outros testes gravam) e mudaria o
    `settings` do processo inteiro. Aqui o escopo vem do monkeypatch."""
    import orchestrator.runtime_settings as rs

    async def _nada(_s: Any) -> list[str]:
        return []

    monkeypatch.setattr(rs, "aplicar", _nada)


def _como(role: Role) -> AsyncClient:
    app.dependency_overrides[deps.get_principal] = lambda: deps.Principal(
        id="u1", email=f"{role.value}@x", role=role, is_service=False
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _trilha(action: str) -> list[AuditLogRow]:
    async with session() as s:
        return list(
            (await s.exec(select(AuditLogRow).where(col(AuditLogRow.action) == action))).all()
        )


# ------------------------------------------------------------- 1. cai scan com gates


async def test_cli_cai_scan_recusa_alvo_fora_do_escopo(
    monkeypatch: pytest.MonkeyPatch, sem_runtime: None
) -> None:
    # Mutação: tirar `gates_do_scan(...)` de `_gates_e_auditoria` -> não levanta.
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    t = Target(asset_type=AssetType.URL, value="http://127.0.0.1:3000/")
    with pytest.raises(GateRecusado) as e:
        await cai_cli._gates_e_auditoria(t, None, None, uuid4())
    assert e.value.status == 403
    assert "rejeitado pela policy" in e.value.detalhe


async def test_cli_cai_scan_exige_authorization_ref(
    escopo_aberto: None, sem_runtime: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REQUIRE_AUTH_REF", True)
    t = Target(asset_type=AssetType.URL, value="https://app.exemplo.test/")
    with pytest.raises(GateRecusado, match="authorization_ref"):
        await cai_cli._gates_e_auditoria(t, None, None, uuid4())


async def test_cli_cai_scan_grava_scan_create_na_trilha(
    escopo_aberto: None, sem_runtime: None
) -> None:
    # Mutação: tirar o `log_audit_event` de `_gates_e_auditoria` -> nenhuma linha.
    sid = uuid4()
    t = Target(asset_type=AssetType.URL, value="https://app.exemplo.test/")
    nomes = await cai_cli._gates_e_auditoria(t, "CHG-42", None, sid)
    assert nomes == ["zap"]  # lista padrão do tipo, como antes
    linhas = [r for r in await _trilha("scan.create") if r.resource_id == sid]
    assert len(linhas) == 1
    assert linhas[0].authorization_ref == "CHG-42"
    assert linhas[0].actor and linhas[0].actor.startswith("cli:")
    assert linhas[0].metadata_json["via"] == "cai scan"


def test_cli_cai_scan_recusado_sai_2_sem_rodar_o_pipeline(
    monkeypatch: pytest.MonkeyPatch, sem_runtime: None
) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")

    async def _nao(*a: Any, **k: Any) -> Any:
        raise AssertionError("run_scan rodou com o alvo recusado")

    monkeypatch.setattr(cai_cli, "run_scan", _nao)
    r = CliRunner().invoke(cai_cli.app, ["scan", "http://127.0.0.1:3000/"])
    assert r.exit_code == 2, r.output
    assert "scan recusado" in r.output


def test_cli_cai_scan_help_diz_a_verdade() -> None:
    texto = inspect.getsource(cai_cli.scan)
    assert "host|url|domain" not in texto
    assert "rota AI local" not in texto
    for t in AssetType:
        assert t.value in cai_cli._TIPOS


# ---------------------------------------------- 2. roqueshield: --type e --profile


def _ajuda(*args: str) -> str:
    r = CliRunner().invoke(cliente_cli.app, [*args, "--help"], terminal_width=400)
    assert r.exit_code == 0, r.output
    return " ".join(r.output.split())


def test_roqueshield_type_lista_os_tipos_que_tem_scanner() -> None:
    # Mutação: voltar o help antigo (sem port, com k8s_resource) -> reprova.
    ajuda = _ajuda("scan", "start")
    escaneaveis = {t.value for t in AssetType if resolve_scanners(None, t, "web")}
    assert "url|domain|host|port|image|repo" in ajuda
    assert {"url", "domain", "host", "port", "image", "repo"} == escaneaveis
    assert "k8s_resource" not in ajuda


def test_roqueshield_profile_lista_os_perfis_do_pipeline() -> None:
    ajuda = _ajuda("scan", "start")
    assert "|".join(PERFIS_DO_SCAN) in ajuda


def test_roqueshield_settings_scope_diz_que_ler_exige_config_manage() -> None:
    ajuda = _ajuda("settings", "scope")
    assert "Ler e trocar exigem config:manage" in ajuda
    assert "TARGET_ALLOWLIST" in ajuda


# --------------------------------------- 3. k8s_resource e scanner desconhecido


def test_k8s_resource_nao_cai_mais_no_nmap() -> None:
    # Mutação: devolver o `or ["nmap"]` no fim da resolução -> reprova.
    nomes, pulados = resolve_scanners_com_motivo(None, AssetType.K8S_RESOURCE, "full")
    assert nomes == []
    assert SEM_SCANNER in pulados
    assert "k8s_resource" in pulados[SEM_SCANNER]


def test_scanner_pedido_desconhecido_ou_incompativel_tem_motivo() -> None:
    nomes, pulados = resolve_scanners_com_motivo(["bogus", "trivy", "nmap"], AssetType.HOST)
    assert nomes == ["nmap"]
    assert "desconhecido" in pulados["bogus"]
    assert "não aceita asset_type host" in pulados["trivy"]


def test_build_adapters_registra_o_desconhecido() -> None:
    # Mutação: tirar o `skipped[n] = ...` de `_build_adapters` -> reprova.
    pulados: dict[str, str] = {}
    adapters = pipelines._build_adapters(["bogus", "trivy"], pulados)
    assert [a.name for a in adapters] == ["trivy"]
    assert "bogus" in pulados


class _AdapterQueRoda:
    name = "nmap"

    async def health(self) -> bool:
        return True

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        return ScanHandle(adapter=self.name, native_id="x")

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        return ScanStatus.DONE

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        return RawResults(adapter=self.name, payload="ok")

    async def normalize(self, raw: RawResults) -> list[Finding]:
        return []


async def test_run_scan_k8s_termina_failed_com_motivo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "REPORTS_DIR", tmp_path)
    t = Target(asset_type=AssetType.K8S_RESOURCE, value="default/deploy/api")
    r = await pipelines.run_scan(t, skip_ai=True, profile="full")
    assert r.scanners_ran == []
    assert SEM_SCANNER in r.scanners_skipped
    assert not r.coverage_is_complete
    async with session() as s:
        linha = await s.get(ScanRow, r.scan_id)
    assert linha is not None and linha.state == "failed"


async def test_run_scan_desconhecido_entra_em_scanners_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Mutação: tirar o laço que copia `pulados_na_resolucao` para o resultado.
    monkeypatch.setattr(settings, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(
        pipelines, "_build_adapters", lambda names, skipped=None: [_AdapterQueRoda()]
    )
    t = Target(asset_type=AssetType.HOST, value="10.9.9.9")
    r = await pipelines.run_scan(t, scanners=["bogus", "nmap"], skip_ai=True)
    assert r.scanners_ran == ["nmap"]
    assert "bogus" in r.scanners_skipped
    assert not r.coverage_is_complete


# ------------------------------------------------------------------- 4. perfis


@pytest.mark.parametrize("perfil", ["cloud", "qualquer", ""])
def test_perfil_que_nao_existe_e_422(perfil: str) -> None:
    # Mutação: `validar_perfil` aceitar qualquer string -> não levanta.
    with pytest.raises(GateRecusado) as e:
        perfil_do_scan(perfil)
    assert e.value.status == 422
    assert "aceitos: web, network, full, active, exposure" in e.value.detalhe


def test_perfil_exposure_resolve_para_o_pipeline_osint() -> None:
    # Mutação: tirar o desvio para `_resolve_exposure` -> volta a lista web (zap...).
    nomes, pulados = resolve_scanners_com_motivo(None, AssetType.URL, "exposure")
    assert nomes == SCANNERS_EXPOSURE and not pulados
    _, pulados = resolve_scanners_com_motivo(None, AssetType.IMAGE, "exposure")
    assert SEM_SCANNER in pulados
    _, pulados = resolve_scanners_com_motivo(["zap"], AssetType.URL, "exposure")
    assert "zap" in pulados


async def test_run_scan_exposure_roda_o_osint_no_mesmo_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mutação: tirar o desvio de `run_scan` para `_run_exposure_como_scan` -> o
    # pipeline OSINT não é chamado (e o zap é construído).
    from orchestrator.jobs import exposure as exposure_job

    chamado: dict[str, Any] = {}

    async def _osint(**kw: Any) -> pipelines.ScanResult:
        chamado.update(kw)
        r = pipelines.ScanResult(scan_id=kw["scan_id"], target=kw["target"])
        r.scanners_ran.append("dnstwist")
        return r

    monkeypatch.setattr(exposure_job, "run_exposure_scan", _osint)
    monkeypatch.setattr(
        pipelines, "_build_adapters", lambda *a, **k: pytest.fail("pipeline de scan rodou")
    )
    sid = uuid4()
    t = Target(asset_type=AssetType.URL, value="https://App.Exemplo.test:8443/x")
    r = await pipelines.run_scan(t, skip_ai=True, profile="exposure", scan_id=sid)
    assert r.scanners_ran == ["dnstwist"]
    assert chamado["scan_id"] == sid and chamado["target"] is t
    assert chamado["domains"] == ["app.exemplo.test"]
    assert chamado["dorks"] == ['"app.exemplo.test"']


def test_perfil_normaliza() -> None:
    assert perfil_do_scan(" FULL ") == "full"


def test_scanners_do_scan_recusa_k8s_com_422() -> None:
    with pytest.raises(GateRecusado) as e:
        scanners_do_scan(None, AssetType.K8S_RESOURCE, "web")
    assert e.value.status == 422


def test_mcp_so_oferece_o_que_existe() -> None:
    # Mutação: devolver "exposure" ao enum do MCP -> reprova.
    props = FERRAMENTAS_DE_ACAO[0]["inputSchema"]["properties"]
    assert tuple(props["profile"]["enum"]) == PERFIS_DO_SCAN
    for tipo in props["asset_type"]["enum"]:
        assert resolve_scanners(None, AssetType(tipo), "web"), tipo


async def test_post_scans_com_profile_exposure_enfileira_o_osint(
    escopo_aberto: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # O roqueos-front manda `profile: exposure` no POST /scans: tem que existir.
    enfileirado: dict[str, Any] = {}

    class _Pool:
        async def enqueue_job(self, *a: Any, **k: Any) -> None:
            enfileirado.update(k)

    async def _pool(*a: Any, **k: Any) -> _Pool:
        return _Pool()

    monkeypatch.setattr(scans_router, "create_pool", _pool)
    alvo = TargetRow(asset_type="domain", value="exemplo.test")
    async with session() as s:
        s.add(alvo)
        await s.commit()
    async with _como(Role.OPERATOR) as c:
        r = await c.post("/scans", json={"target_id": str(alvo.id), "profile": "Exposure"})
    assert r.status_code == 202, r.text
    assert r.json()["profile"] == "exposure"
    assert enfileirado["profile"] == "exposure"
    assert enfileirado["scanners"] == SCANNERS_EXPOSURE


async def test_post_scans_exposure_em_imagem_e_422(escopo_aberto: None) -> None:
    alvo = TargetRow(asset_type="image", value="nginx:1.27")
    async with session() as s:
        s.add(alvo)
        await s.commit()
    async with _como(Role.OPERATOR) as c:
        r = await c.post("/scans", json={"target_id": str(alvo.id), "profile": "exposure"})
    assert r.status_code == 422, r.text
    assert "domínio" in r.json()["detail"]


async def test_post_scans_com_scanner_inexistente_e_422(escopo_aberto: None) -> None:
    alvo = TargetRow(asset_type="url", value="https://app2.exemplo.test/")
    async with session() as s:
        s.add(alvo)
        await s.commit()
    async with _como(Role.OPERATOR) as c:
        r = await c.post("/scans", json={"target_id": str(alvo.id), "scanners": ["zapp"]})
    assert r.status_code == 422, r.text
    assert "zapp" in r.json()["detail"]


# ------------------------------------------------------- 5. leitura da trilha


@pytest.mark.parametrize(
    ("role", "esperado"),
    [(Role.VIEWER, 403), (Role.OPERATOR, 403), (Role.AUDITOR, 200), (Role.ADMIN, 200)],
)
async def test_get_audit_exige_audit_read(role: Role, esperado: int) -> None:
    # Mutação: trocar RequireAuditRead por RequireScansRead -> viewer e operator dão 200.
    async with _como(role) as c:
        r = await c.get("/audit?limit=5")
    assert r.status_code == esperado, r.text


async def test_get_audit_devolve_a_trilha_mais_recente_primeiro() -> None:
    rid = uuid4()
    from orchestrator.audit import log_audit_event

    async with session() as s:
        for i in range(3):
            await log_audit_event(
                s, action="w2.teste", actor="a@x", resource_id=rid, metadata={"i": i}
            )
            await s.commit()
    async with _como(Role.AUDITOR) as c:
        r = await c.get(f"/audit?action=w2.teste&resource_id={rid}")
    corpo = r.json()
    assert corpo["total"] == 3
    datas = [i["created_at"] for i in corpo["items"]]
    assert datas == sorted(datas, reverse=True)


def test_get_audit_sem_credencial_e_401() -> None:
    # A rota nasce com o mesmo `get_principal` de todas: sem credencial, 401.
    from fastapi.testclient import TestClient

    r = TestClient(app).get("/audit")
    assert r.status_code == 401


# ------------------------------------------------ 6. fallback para a nuvem


def test_allow_cloud_fallback_default_e_false(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mutação: voltar o default para True -> reprova.
    monkeypatch.delenv("ALLOW_CLOUD_FALLBACK", raising=False)
    assert Settings(_env_file=None).ALLOW_CLOUD_FALLBACK is False  # type: ignore[call-arg]


def test_env_example_traz_o_mesmo_default() -> None:
    linhas = (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "ALLOW_CLOUD_FALLBACK=false" in linhas


# ---------------------------------------------- 7. exposure e DefectDojo na trilha


async def test_post_exposure_scan_grava_na_trilha(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mutação: tirar o `log_audit_event` do router de exposure -> nenhuma linha.
    class _Job:
        job_id = "j-1"

    class _Pool:
        async def enqueue_job(self, *a: Any, **k: Any) -> _Job:
            return _Job()

    async def _pool(*a: Any, **k: Any) -> _Pool:
        return _Pool()

    monkeypatch.setattr(exposure_router, "create_pool", _pool)
    antes = len(await _trilha("exposure.scan"))
    async with _como(Role.OPERATOR) as c:
        r = await c.post(
            "/exposure/scan", json={"company_name": "W2 SA", "domains": ["w2.example"]}
        )
    assert r.status_code == 202, r.text
    linhas = await _trilha("exposure.scan")
    assert len(linhas) == antes + 1
    assert linhas[-1].actor == "operator@x"


async def test_export_defectdojo_grava_na_trilha_antes_de_enviar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mutação: tirar o `log_audit_event` do export -> nenhuma linha, nem na falha.
    from orchestrator.reporting.exporters import defectdojo

    alvo = TargetRow(asset_type="url", value="https://dojo-alvo.example/")
    scan = ScanRow(target_id=alvo.id, authorization_ref="CHG-7")
    async with session() as s:
        s.add(alvo)
        s.add(scan)
        await s.commit()

    async def _falha(scan_id: UUID, **k: Any) -> dict:
        raise RuntimeError("dojo fora")

    monkeypatch.setattr(defectdojo, "export_scan", _falha)
    async with _como(Role.OPERATOR) as c:
        r = await c.post(f"/reports/{scan.id}/export/defectdojo")
    assert r.status_code == 500
    linhas = [r for r in await _trilha("scan.export.defectdojo") if r.resource_id == scan.id]
    assert len(linhas) == 1
    assert linhas[0].authorization_ref == "CHG-7"


# ---------------------------------------------------------- 8. dedup determinístico


def _achado(rule: str, sev: Severity, tool: str, conf: Confidence = Confidence.FIRM) -> Finding:
    return Finding(
        scan_id=uuid4(),
        target=Target(asset_type=AssetType.URL, value="https://a.example"),
        source_tool=tool,
        source_rule_id=rule,
        title=f"{tool} {rule}",
        description="achado de teste",
        severity=sev,
        confidence=conf,
    )


def test_heuristic_dedup_nao_depende_da_ordem_de_chegada() -> None:
    # Mutação: voltar ao "primeiro que chegou fica" e sem ordenar a saída -> reprova.
    base = [
        _achado("r1", Severity.MEDIUM, "zap"),
        _achado("r1", Severity.MEDIUM, "nuclei"),  # mesmo deduped_key, mesma severity
        _achado("r2", Severity.HIGH, "zap"),
        _achado("r3", Severity.LOW, "nuclei"),
        _achado("r4", Severity.HIGH, "nuclei"),
    ]
    esperado = [(f.deduped_key, f.source_tool) for f in heuristic_dedup(base)]
    rng = random.Random(7)  # noqa: S311  embaralhar teste, não cripto
    for _ in range(20):
        embaralhado = base[:]
        rng.shuffle(embaralhado)
        assert [(f.deduped_key, f.source_tool) for f in heuristic_dedup(embaralhado)] == esperado
    sevs = [f.severity for f in heuristic_dedup(base)]
    assert sevs == ["high", "high", "medium", "low"]


def test_heuristic_dedup_empate_fica_com_a_maior_confidence() -> None:
    a = _achado("r1", Severity.MEDIUM, "zap", Confidence.TENTATIVE)
    b = _achado("r1", Severity.MEDIUM, "zap", Confidence.CERTAIN)
    assert heuristic_dedup([a, b])[0] is b
    assert heuristic_dedup([b, a])[0] is b


def test_heuristic_dedup_aceita_gerador() -> None:
    a = _achado("r1", Severity.LOW, "zap")
    assert len(heuristic_dedup(x for x in [a])) == 1


# ------------------------------------------- 9. link-local: o que o código faz


def test_link_local_nunca_vira_alvo_nem_com_allowlist_nem_sem_lab_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A docstring antiga de `liberavel_pela_tela` dizia que pela variável de ambiente
    # o operador "ainda pode tudo". Para link-local não pode.
    # Mutação: tirar o ramo "link_local" de `_guarda_dura` -> passa e reprova.
    monkeypatch.setattr(settings, "LAB_ONLY", False)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "169.254.169.254,169.254.0.0/16")
    with pytest.raises(tv.AlvoForaDoEscopo) as e:
        tv.validate_target_value("http://169.254.169.254/latest/", asset_type="url")
    assert "link-local" in str(e.value)
    assert tv.liberavel_pela_tela(e.value) is False


def test_loopback_so_pelo_endereco_na_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "127.0.0.1")
    tv.validate_target_value("http://127.0.0.1:3000/", asset_type="url")


def test_docstring_de_liberavel_nao_promete_o_que_o_codigo_nao_faz() -> None:
    doc = tv.liberavel_pela_tela.__doc__ or ""
    assert "pode tudo" not in doc
    assert "_guarda_dura" in doc
    for nome in tv._FORBIDDEN_HOSTNAMES:
        assert nome in doc, nome


# ------------------------------------------------------- reuso, não duplicação


def test_router_e_cli_usam_o_mesmo_gate() -> None:
    fonte_router = inspect.getsource(scans_router.create_scan)
    fonte_cli = inspect.getsource(cai_cli._gates_e_auditoria)
    assert "gates_do_scan(" in fonte_router and "gates_do_scan(" in fonte_cli
    assert "validate_target_value(target.value" not in fonte_router
    assert gates_do_scan is scans_router.gates_do_scan
