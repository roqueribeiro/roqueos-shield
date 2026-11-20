"""Código enviado para scan e o veredito do gate.

Cada teste diz a mutação que o reprova. Os dois lados da regra do silêncio: o envio
hostil é recusado sem extrair nada, e um envio que não pôde ser preparado vira
`scanners_skipped` e scan `failed`, nunca "zero achado".
"""

from __future__ import annotations

import asyncio
import io
import json
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import col, select

from orchestrator import codigo_enviado
from orchestrator.api import deps
from orchestrator.api.routers import scans as scans_router
from orchestrator.cliente.empacotar import empacotar, listar
from orchestrator.cliente.mcp_nucleo import Servidor
from orchestrator.config import settings
from orchestrator.domain import codigo
from orchestrator.domain.codigo import CodigoRecusado
from orchestrator.domain.roles import Role
from orchestrator.domain.schemas import (
    AssetType,
    Finding,
    RawResults,
    ScanHandle,
    ScanStatus,
    Severity,
    Target,
)
from orchestrator.domain.target_validator import TargetValidationError, validate_target_value
from orchestrator.jobs import pipelines, workers
from orchestrator.main import app
from orchestrator.persistence.db import init_db, session
from orchestrator.persistence.models import (
    AuditLogRow,
    FindingRow,
    FindingStatusRow,
    ScanRow,
    ScanState,
    TargetRow,
)

_MB = 1024 * 1024


@pytest_asyncio.fixture(autouse=True)
async def _banco(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "REPORTS_DIR", tmp_path / "reports")
    await init_db()
    yield
    app.dependency_overrides.clear()


def _como(role: Role) -> AsyncClient:
    app.dependency_overrides[deps.get_principal] = lambda: deps.Principal(
        id="u1", email=f"{role.value}@x", role=role, is_service=False
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _tar(membros: list[tarfile.TarInfo | tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for m in membros:
            if isinstance(m, tuple):
                info = tarfile.TarInfo(m[0])
                info.size = len(m[1])
                tar.addfile(info, io.BytesIO(m[1]))
            else:
                tar.addfile(m)
    return buf.getvalue()


def _link(nome: str, alvo: str, tipo: bytes = tarfile.SYMTYPE) -> tarfile.TarInfo:
    i = tarfile.TarInfo(nome)
    i.type = tipo
    i.linkname = alvo
    return i


def _inspecionar(dados: bytes, tmp_path: Path, **kw: int) -> codigo.Inventario:
    arq = tmp_path / "envio.tar.gz"
    arq.write_bytes(dados)
    return codigo.inspecionar(
        arq, max_arquivos=kw.get("max_arquivos", 100), max_bytes=kw.get("max_bytes", _MB)
    )


# --------------------------------------------------------------- o tarball hostil


@pytest.mark.parametrize(
    ("membros", "trecho"),
    [
        ([("../fora.py", b"x")], "fora da raiz"),
        ([("/etc/cron.d/x", b"x")], "fora da raiz"),
        ([("a/../../fora.py", b"x")], "fora da raiz"),
        ([_link("l", "/etc/passwd")], "link"),
        ([_link("a/l", "../../segredo")], "link"),
        ([_link("h", "../fora", tarfile.LNKTYPE)], "link"),
    ],
)
def test_inspecionar_recusa_o_que_escapa_da_raiz(
    membros: list[Any], trecho: str, tmp_path: Path
) -> None:
    # Mutação: `_dentro` devolvendo sempre True -> estes passam e o extractall escreve
    # fora da pasta (o filtro `data` ainda seguraria, mas a primeira camada sumiu).
    with pytest.raises(CodigoRecusado, match=trecho):
        _inspecionar(_tar(membros), tmp_path)


def test_inspecionar_recusa_dispositivo(tmp_path: Path) -> None:
    dev = tarfile.TarInfo("dev/zero")
    dev.type = tarfile.CHRTYPE
    with pytest.raises(CodigoRecusado, match="tipo de membro"):
        _inspecionar(_tar([dev]), tmp_path)


def test_inspecionar_recusa_bomba_por_bytes_e_por_arquivos(tmp_path: Path) -> None:
    # Mutação: tirar o teto de `total` -> uma bomba de zeros enche o /tmp do worker.
    zeros = b"\0" * (2 * _MB)  # comprime para quase nada
    dados = _tar([("grande.bin", zeros)])
    assert len(dados) < 64 * 1024
    with pytest.raises(CodigoRecusado, match="descomprimido"):
        _inspecionar(dados, tmp_path, max_bytes=_MB)
    muitos = _tar([(f"f{i}.py", b"x") for i in range(11)])
    with pytest.raises(CodigoRecusado, match="mais de 10 arquivos"):
        _inspecionar(muitos, tmp_path, max_arquivos=10)


def test_inspecionar_recusa_envio_sem_arquivo_e_lixo(tmp_path: Path) -> None:
    # Zero arquivo não é código limpo: é envio quebrado.
    pasta = tarfile.TarInfo("vazia")
    pasta.type = tarfile.DIRTYPE
    with pytest.raises(CodigoRecusado, match="nenhum arquivo"):
        _inspecionar(_tar([pasta]), tmp_path)
    with pytest.raises(CodigoRecusado, match="legível"):
        _inspecionar(b"isto nao e gzip", tmp_path)


def test_inspecionar_aceita_arvore_normal_e_link_interno(tmp_path: Path) -> None:
    inv = _inspecionar(
        _tar([("src/app.py", b"print(1)\n"), ("README.md", b"# x\n"), _link("src/l", "app.py")]),
        tmp_path,
    )
    assert inv.arquivos == 2
    assert inv.bytes_descomprimidos == len(b"print(1)\n") + len(b"# x\n")


def test_extrair_e_fotografar_fazem_um_commit(tmp_path: Path) -> None:
    arq = tmp_path / "e.tar.gz"
    arq.write_bytes(_tar([("src/app.py", b"print(1)\n")]))
    raiz = tmp_path / "repo"
    codigo.extrair(arq, raiz, max_arquivos=10, max_bytes=_MB)
    codigo.fotografar_em_git(raiz)
    log = subprocess.run(
        ["git", "-C", str(raiz), "log", "--oneline"], capture_output=True, text=True, check=True
    )
    assert len(log.stdout.strip().splitlines()) == 1
    listados = subprocess.run(
        ["git", "-C", str(raiz), "ls-files"], capture_output=True, text=True, check=True
    )
    assert listados.stdout.split() == ["src/app.py"]


def test_fotografar_recusa_envio_com_pasta_git(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    with pytest.raises(CodigoRecusado, match=".git"):
        codigo.fotografar_em_git(tmp_path)


# --------------------------------------------------------------- identidade estável


def _achado(raiz: Path, arquivo: str, regra: str = "sqli") -> Finding:
    return Finding(
        scan_id=uuid4(),
        target=Target(asset_type=AssetType.REPO, value=f"{raiz}/{arquivo}:7"),
        source_tool="semgrep",
        source_rule_id=regra,
        title=f"SQL em {raiz}/{arquivo}",
        description="d",
        severity=Severity.HIGH,
    )


def test_reescrever_alvo_da_a_mesma_chave_em_envios_diferentes(tmp_path: Path) -> None:
    # Mutação: não zerar `deduped_key` antes de revalidar -> a chave continua a da
    # pasta temporária, todo achado é "novo" em todo envio e o gate nunca separa a
    # dívida antiga do que acabou de entrar.
    alvo = Target(asset_type=AssetType.REPO, value="code://loja")
    a = codigo.reescrever_alvo([_achado(tmp_path / "um", "db.py")], tmp_path / "um", alvo)[0]
    b = codigo.reescrever_alvo([_achado(tmp_path / "dois", "db.py")], tmp_path / "dois", alvo)[0]
    assert a.deduped_key == b.deduped_key
    assert a.target.value == "code://loja/db.py:7"
    assert str(tmp_path) not in a.title


def test_validador_aceita_code_e_recusa_nome_ruim() -> None:
    assert validate_target_value("code://Loja-Web", asset_type="repo") == "code://loja-web"
    for ruim in ("code://", "code://../x", "code://a/b", "code://-x"):
        with pytest.raises(TargetValidationError):
            validate_target_value(ruim, asset_type="repo")


# --------------------------------------------------------------- a rota de envio


async def test_upload_grava_cria_o_alvo_e_audita() -> None:
    dados = _tar([("app.py", b"print(1)\n")])
    async with _como(Role.OPERATOR) as c:
        r = await c.post(
            "/code/loja/uploads", content=dados, headers={"Content-Type": "application/gzip"}
        )
        assert r.status_code == 201, r.text
        corpo = r.json()
        r2 = await c.post(
            "/code/loja/uploads", content=dados, headers={"Content-Type": "application/gzip"}
        )
    assert corpo["target_value"] == "code://loja"
    assert corpo["arquivos"] == 1
    assert r2.json()["target_id"] == corpo["target_id"]  # o alvo é o mesmo projeto
    assert codigo_enviado.ler(corpo["upload_id"]) is not None
    async with session() as s:
        trilha = (
            await s.exec(
                select(AuditLogRow).where(
                    col(AuditLogRow.action) == "code.upload",
                    col(AuditLogRow.resource_id) == UUID(corpo["target_id"]),
                )
            )
        ).all()
    # O banco é dividido com outros testes: o alvo `code://loja` pode já ter envios.
    envios = {e.metadata_json["upload_id"] for e in trilha}
    assert {corpo["upload_id"], r2.json()["upload_id"]} <= envios
    assert any(e.metadata_json["sha256"] == corpo["sha256"] for e in trilha)


@pytest.mark.parametrize(
    ("tipo", "dados", "status"),
    [
        ("text/plain", b"x", 415),
        ("application/gzip", b"", 422),
        ("application/gzip", b"isto nao e gzip", 422),
    ],
)
async def test_upload_recusa_o_que_nao_serve(tipo: str, dados: bytes, status: int) -> None:
    async with _como(Role.OPERATOR) as c:
        r = await c.post("/code/loja/uploads", content=dados, headers={"Content-Type": tipo})
    assert r.status_code == status, r.text
    assert list(codigo_enviado.pasta().iterdir()) == []  # nada sobra no disco


async def test_upload_recusa_traversal_sem_deixar_nada(tmp_path: Path) -> None:
    async with _como(Role.OPERATOR) as c:
        r = await c.post(
            "/code/loja/uploads",
            content=_tar([("../fora.py", b"x")]),
            headers={"Content-Type": "application/gzip"},
        )
    assert r.status_code == 422
    assert "fora da raiz" in r.json()["detail"]
    assert list(codigo_enviado.pasta().iterdir()) == []


async def test_upload_acima_do_teto_e_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CODE_UPLOAD_MAX_MB", 0)
    async with _como(Role.OPERATOR) as c:
        r = await c.post(
            "/code/loja/uploads",
            content=_tar([("a.py", b"x")]),
            headers={"Content-Type": "application/gzip"},
        )
    assert r.status_code == 413


async def test_upload_exige_scans_run() -> None:
    async with _como(Role.VIEWER) as c:
        r = await c.post(
            "/code/loja/uploads",
            content=_tar([("a.py", b"x")]),
            headers={"Content-Type": "application/gzip"},
        )
    assert r.status_code == 403


# --------------------------------------------------------------- o POST /scans


async def _envio(projeto: str = "loja") -> dict[str, Any]:
    async with _como(Role.OPERATOR) as c:
        r = await c.post(
            f"/code/{projeto}/uploads",
            content=_tar([("app.py", b"print(1)\n")]),
            headers={"Content-Type": "application/gzip"},
        )
    assert r.status_code == 201, r.text
    return dict(r.json())


@pytest.fixture
def fila(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    enfileirado: dict[str, Any] = {}

    class _Pool:
        async def enqueue_job(self, *a: Any, **k: Any) -> None:
            enfileirado.update(k)

    async def _pool(*a: Any, **k: Any) -> _Pool:
        return _Pool()

    monkeypatch.setattr(scans_router, "create_pool", _pool)
    monkeypatch.setattr(settings, "REQUIRE_AUTH_REF", False)
    return enfileirado


async def test_scan_de_codigo_leva_o_envio_ao_worker(fila: dict[str, Any]) -> None:
    envio = await _envio()
    async with _como(Role.OPERATOR) as c:
        r = await c.post(
            "/scans",
            json={"target_id": envio["target_id"], "code_upload_id": envio["upload_id"]},
        )
    assert r.status_code == 202, r.text
    assert fila["code_upload_id"] == envio["upload_id"]
    assert fila["target_value"] == "code://loja"


async def test_scan_de_codigo_sem_envio_ou_com_envio_trocado_e_recusado(
    fila: dict[str, Any],
) -> None:
    # Mutação: `_envio_do_scan` devolvendo None para alvo code:// -> o worker recebe um
    # alvo sem código, nenhum scanner acha nada e o scan fecha "limpo".
    envio = await _envio("loja")
    outro = await _envio("outra")
    async with _como(Role.OPERATOR) as c:
        sem = await c.post("/scans", json={"target_id": envio["target_id"]})
        trocado = await c.post(
            "/scans",
            json={"target_id": envio["target_id"], "code_upload_id": outro["upload_id"]},
        )
        inexistente = await c.post(
            "/scans", json={"target_id": envio["target_id"], "code_upload_id": str(uuid4())}
        )
    assert sem.status_code == 422
    assert trocado.status_code == 422
    assert inexistente.status_code == 404
    assert not fila


# --------------------------------------------------------------- o worker e o pipeline


class _GitleaksFalso:
    name = "gitleaks"

    def __init__(self) -> None:
        self.visto: str | None = None

    async def health(self) -> bool:
        return True

    async def start_scan(self, target: Target, options: dict[str, Any]) -> ScanHandle:
        self.visto = target.value
        return ScanHandle(adapter=self.name, native_id="x")

    async def poll(self, handle: ScanHandle) -> ScanStatus:
        return ScanStatus.DONE

    async def fetch_results(self, handle: ScanHandle) -> RawResults:
        return RawResults(adapter=self.name, payload="ok")

    async def normalize(self, raw: RawResults) -> list[Finding]:
        assert self.visto is not None
        return [_achado(Path(self.visto), "config.py", "aws-key")]


async def test_pipeline_escaneia_a_pasta_e_devolve_o_alvo_logico(tmp_path: Path) -> None:
    # Mutação: passar `target` em vez de `alvo_do_adapter` ao _run_adapter -> o
    # scanner recebe `code://loja`, que não é pasta nem URL, e não acha nada.
    raiz = tmp_path / "repo"
    raiz.mkdir()
    falso = _GitleaksFalso()
    alvo = Target(asset_type=AssetType.REPO, value="code://loja")
    r = await pipelines.run_scan(alvo, adapters=[falso], skip_ai=True, code_root=raiz)
    assert falso.visto == str(raiz)
    valores = {f.target.value for f in r.findings}
    assert "code://loja/config.py:7" in valores
    assert not any(str(raiz) in v for v in valores)
    # O histórico não veio: a lacuna é declarada, não omitida.
    lacunas = [f for f in r.findings if f.source_rule_id == "codigo-enviado-coverage-gap"]
    assert len(lacunas) == 1
    assert "histórico" in lacunas[0].description


async def test_envio_que_nao_prepara_vira_scanner_pulado_e_scan_failed(tmp_path: Path) -> None:
    # Mutação: ignorar `code_error` no run_scan -> os adapters rodam numa pasta que
    # não existe, ou não rodam e o scan fecha DONE com zero achado.
    alvo = Target(asset_type=AssetType.REPO, value="code://loja")
    r = await pipelines.run_scan(
        alvo, adapters=[_GitleaksFalso()], skip_ai=True, code_error="tarball corrompido"
    )
    assert r.scanners_ran == []
    assert "tarball corrompido" in r.scanners_skipped["gitleaks"]
    async with session() as s:
        linha = await s.get(ScanRow, r.scan_id)
    assert linha is not None and linha.state == ScanState.FAILED.value


def test_preparar_codigo_de_envio_sumido_ou_corrompido_devolve_erro(tmp_path: Path) -> None:
    raiz, erro, tmp = workers._preparar_codigo(str(uuid4()))
    assert raiz is None and erro and "não existe" in erro
    uid = str(uuid4())
    codigo_enviado.tarball(uid).write_bytes(b"lixo")
    codigo_enviado.gravar_meta(
        codigo_enviado.Envio(uid, "loja", "h", 4, 1, 1, datetime.now(UTC).isoformat(), "x")
    )
    raiz, erro, tmp = workers._preparar_codigo(uid)
    assert raiz is None and erro and "legível" in erro
    assert tmp is not None


async def test_job_apaga_o_envio_depois_do_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    # Uso único: código de cliente não fica no disco do scanner depois do scan.
    envio = await _envio()
    chamado: dict[str, Any] = {}

    async def _run_scan(target: Target, **kw: Any) -> pipelines.ScanResult:
        chamado.update(kw)
        assert (kw["code_root"] / "app.py").is_file()
        return pipelines.ScanResult(scan_id=uuid4(), target=target)

    monkeypatch.setattr(pipelines, "run_scan", _run_scan)
    import orchestrator.runtime_settings as rs

    async def _nada(_s: Any) -> list[str]:
        return []

    monkeypatch.setattr(rs, "aplicar", _nada)
    await workers.run_scan_job(
        {}, target_value="code://loja", asset_type="repo", code_upload_id=envio["upload_id"]
    )
    assert chamado["code_error"] is None
    assert codigo_enviado.ler(envio["upload_id"]) is None
    assert not chamado["code_root"].exists()


def test_expurgo_apaga_vencido_e_orfao_e_poupa_o_recente() -> None:
    velho, novo, orfao = str(uuid4()), str(uuid4()), str(uuid4())
    for uid, quando in ((velho, datetime.now(UTC) - timedelta(days=3)), (novo, datetime.now(UTC))):
        codigo_enviado.tarball(uid).write_bytes(b"x")
        codigo_enviado.gravar_meta(
            codigo_enviado.Envio(uid, "loja", "h", 1, 1, 1, quando.isoformat(), "x")
        )
    codigo_enviado.tarball(orfao).write_bytes(b"x")
    apagados = set(codigo_enviado.expurgar_vencidos())
    assert apagados == {velho, orfao}
    assert codigo_enviado.ler(novo) is not None


# --------------------------------------------------------------- o veredito do gate


async def _scan(
    alvo: TargetRow,
    achados: list[tuple[str, str]],
    *,
    quando: datetime,
    pulados: dict[str, str] | None = None,
    estado: str = ScanState.DONE.value,
) -> UUID:
    async with session() as s:
        scan = ScanRow(
            target_id=alvo.id,
            state=estado,
            started_at=quando,
            finished_at=quando if estado == ScanState.DONE.value else None,
            scanners_ran=["semgrep"],
            scanners_skipped=pulados or {},
        )
        s.add(scan)
        await s.flush()
        for chave, sev in achados:
            s.add(
                FindingRow(
                    scan_id=scan.id,
                    target_id=alvo.id,
                    deduped_key=chave,
                    source_tool="semgrep",
                    title=f"achado {chave}",
                    severity=sev,
                )
            )
        await s.commit()
        return scan.id


async def _alvo() -> TargetRow:
    async with session() as s:
        a = TargetRow(asset_type="repo", value=f"code://p{uuid4().hex[:8]}")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return a


async def _gate(scan_id: UUID, **params: str) -> dict[str, Any]:
    async with _como(Role.VIEWER) as c:
        r = await c.get(f"/scans/{scan_id}/gate", params=params)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_gate_so_reprova_achado_novo_por_padrao() -> None:
    # Mutação: ignorar a linha de base -> a dívida antiga reprova todo PR.
    alvo = await _alvo()
    t0 = datetime.now(UTC) - timedelta(hours=2)
    base = await _scan(alvo, [("velho", "high")], quando=t0)
    atual = await _scan(
        alvo, [("velho", "high"), ("novo", "critical")], quando=t0 + timedelta(hours=1)
    )
    g = await _gate(atual)
    assert g["verdict"] == "reprovado"
    assert g["baseline_scan_id"] == str(base)
    assert [b["deduped_key"] for b in g["bloqueantes"]] == ["novo"]
    assert (g["novos"], g["conhecidos"]) == (1, 1)
    so_velho = await _scan(alvo, [("velho", "high")], quando=t0 + timedelta(hours=1, minutes=30))
    assert (await _gate(so_velho))["verdict"] == "aprovado"
    assert (await _gate(so_velho, so_novos="false"))["verdict"] == "reprovado"


async def test_gate_cobertura_incompleta_e_nao_medido_nunca_aprovado() -> None:
    # Mutação: checar a cobertura depois dos bloqueantes, ou não checar -> zero achado
    # com o semgrep fora do ar sai "aprovado".
    alvo = await _alvo()
    s = await _scan(alvo, [], quando=datetime.now(UTC), pulados={"gitleaks": "binário ausente"})
    g = await _gate(s)
    assert g["verdict"] == "nao_medido"
    assert "gitleaks" in g["motivo"] or "incompleta" in g["motivo"]


async def test_gate_em_andamento_e_status_assinado() -> None:
    alvo = await _alvo()
    rodando = await _scan(alvo, [], quando=datetime.now(UTC), estado=ScanState.RUNNING.value)
    assert (await _gate(rodando))["verdict"] == "em_andamento"
    feito = await _scan(alvo, [("aceito", "critical")], quando=datetime.now(UTC))
    async with session() as s:
        s.add(FindingStatusRow(deduped_key="aceito", status="risk_accepted"))
        await s.commit()
    g = await _gate(feito)
    assert g["verdict"] == "aprovado"
    assert g["fora_do_gate"] == 1


async def test_gate_fail_on_invalido_e_422() -> None:
    alvo = await _alvo()
    s = await _scan(alvo, [], quando=datetime.now(UTC))
    async with _como(Role.VIEWER) as c:
        r = await c.get(f"/scans/{s}/gate", params={"fail_on": "grave"})
    assert r.status_code == 422


# --------------------------------------------------------------- cliente e MCP


def test_empacotar_respeita_gitignore_e_deixa_git_e_link_de_fora(tmp_path: Path) -> None:
    raiz = tmp_path / "proj"
    (raiz / "src").mkdir(parents=True)
    (raiz / "src" / "app.py").write_text("print(1)\n")
    (raiz / "novo.py").write_text("ainda nao commitado\n")
    (raiz / ".env").write_text("SEGREDO=1\n")
    (raiz / "node_modules").mkdir()
    (raiz / "node_modules" / "lib.js").write_text("x")
    (raiz / ".gitignore").write_text(".env\nnode_modules/\n")
    (raiz / "fora").symlink_to("/etc/hosts")
    subprocess.run(["git", "init", "-q", str(raiz)], check=True)
    subprocess.run(["git", "-C", str(raiz), "add", "src", ".gitignore"], check=True)
    nomes = listar(raiz)
    assert nomes == [".gitignore", "novo.py", "src/app.py"]
    pacote = empacotar(raiz)
    with tarfile.open(fileobj=io.BytesIO(pacote.dados), mode="r:gz") as tar:
        assert sorted(tar.getnames()) == nomes


def test_empacotar_fora_do_git_leva_tudo_menos_a_pasta_git(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x")
    assert listar(tmp_path) == ["a.py"]


class _ApiFalsa:
    def __init__(self, gate: dict[str, Any]) -> None:
        self.gate = gate

    async def get(self, caminho: str) -> Any:
        return self.gate

    async def post(self, caminho: str, corpo: Any = None) -> Any:
        return {}


def test_mcp_scan_code_so_existe_no_stdio() -> None:
    # Por HTTP o servidor MCP roda no shield e não enxerga o disco de quem chama.
    http = {f["name"] for f in Servidor(_ApiFalsa({}), acoes=True).ferramentas()}
    stdio = {f["name"] for f in Servidor(_ApiFalsa({}), local=True).ferramentas()}
    assert "scan_code" not in http
    assert "scan_code" in stdio
    assert "gate_verdict" in http and "gate_verdict" in stdio


async def test_mcp_gate_nao_medido_volta_como_erro() -> None:
    # Mutação: devolver o nao_medido como resultado normal -> o agente lê "sem
    # bloqueantes" e entrega o código.
    srv = Servidor(_ApiFalsa({"verdict": "nao_medido", "motivo": "gitleaks fora"}))
    r = await srv.tratar(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "gate_verdict", "arguments": {"scan_id": str(uuid4())}},
        }
    )
    assert r is not None and r["result"]["isError"] is True
    assert json.loads(r["result"]["content"][0]["text"])["verdict"] == "nao_medido"


def test_reescrever_alvo_tira_o_commit_da_fotografia_da_chave(tmp_path: Path) -> None:
    # Mutação: não remover o sha do `dedup_discriminator` -> o Fingerprint do gitleaks
    # (`<commit>:<arquivo>:<regra>:<linha>`) muda a cada envio e todo segredo conhecido
    # volta como novo. Achado pelo teste ponta a ponta com o gitleaks real.
    alvo = Target(asset_type=AssetType.REPO, value="code://loja")
    chaves = []
    for nome in ("um", "dois"):
        raiz = tmp_path / nome
        raiz.mkdir()
        (raiz / "cfg.py").write_text(f"# {nome}\n")
        codigo.fotografar_em_git(raiz)
        sha = subprocess.run(
            ["git", "-C", str(raiz), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        f = _achado(raiz, "cfg.py", "aws-key").model_copy(
            update={"dedup_discriminator": f"{sha}:cfg.py:aws-key:7", "deduped_key": ""}
        )
        f = Finding.model_validate(f.model_dump())
        chaves.append(codigo.reescrever_alvo([f], raiz, alvo)[0].deduped_key)
    assert chaves[0] == chaves[1]


async def test_scan_com_ai_false_pula_a_ia_no_worker(fila: dict[str, Any]) -> None:
    # Mutação: não repassar `skip_ai` ao job -> o gate de CI espera o LLM triar centenas
    # de achados (medido no shield central: 346 achados, mais de 30 min) e estoura.
    envio = await _envio("loja-ia")
    async with _como(Role.OPERATOR) as c:
        r = await c.post(
            "/scans",
            json={
                "target_id": envio["target_id"],
                "code_upload_id": envio["upload_id"],
                "ai": False,
            },
        )
    assert r.status_code == 202, r.text
    assert fila["skip_ai"] is True
    envio2 = await _envio("loja-ia")
    async with _como(Role.OPERATOR) as c:
        await c.post(
            "/scans", json={"target_id": envio2["target_id"], "code_upload_id": envio2["upload_id"]}
        )
    assert fila["skip_ai"] is False  # o padrão continua com IA


@pytest.mark.parametrize("erro", [asyncio.CancelledError, TimeoutError])
async def test_job_interrompido_fecha_o_scan_como_failed(
    monkeypatch: pytest.MonkeyPatch, erro: type[BaseException]
) -> None:
    # Mutação: tirar o `except BaseException` do run_scan_job -> o scan cujo job o arq
    # matou no job_timeout fica `running` para sempre e trava o reconcile do server.
    alvo = await _alvo()
    async with session() as s:
        row = ScanRow(target_id=alvo.id, state=ScanState.RUNNING.value)
        s.add(row)
        await s.commit()
        await s.refresh(row)

    async def _morre(target: Target, **kw: Any) -> pipelines.ScanResult:
        raise erro()

    monkeypatch.setattr(pipelines, "run_scan", _morre)
    import orchestrator.runtime_settings as rs

    async def _nada(_s: Any) -> list[str]:
        return []

    monkeypatch.setattr(rs, "aplicar", _nada)
    with pytest.raises(erro):
        await workers.run_scan_job(
            {}, target_value=alvo.value, asset_type="repo", scan_id=str(row.id)
        )
    async with session() as s:
        fim = await s.get(ScanRow, row.id)
    assert fim is not None and fim.state == ScanState.FAILED.value
    assert any("interrompido" in e for e in fim.errors)
    assert fim.finished_at is not None
