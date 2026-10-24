"""GOAL-SHIELD-04 (Issues #11 e #12): rate limit, redação de credencial e não-root."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from orchestrator.api import ratelimit
from orchestrator.api.deps import Principal
from orchestrator.domain.redaction import REDACTED, redact, redact_argv, redaction_processor
from orchestrator.domain.roles import Role

RAIZ = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- redação (#11 c)


def test_argv_do_scanner_perde_o_valor_das_flags_secretas_e_so_ele():
    argv = [
        "nuclei",
        "-u",
        "https://admin:s3nh4@app.example/login",
        "-H",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def",
        "--cookie=session=abc123",
        "-p",
        "443",
        "--header",
        "X-Api-Key: k-777",
        "-severity",
        "high",
    ]
    assert redact_argv(argv) == [
        "nuclei",
        "-u",
        f"https://{REDACTED}@app.example/login",
        "-H",
        REDACTED,
        f"--cookie={REDACTED}",
        "-p",
        "443",
        "--header",
        REDACTED,
        "-severity",
        "high",
    ]


def test_texto_solto_url_bearer_e_chave_valor():
    assert redact("postgres://cai:supersecreta@db:5432/cai") == f"postgres://{REDACTED}@db:5432/cai"
    assert redact("falhou com Bearer abcdef123456") == f"falhou com Bearer {REDACTED}"
    assert redact("GET /x?api_key=AKIA123&page=2") == f"GET /x?api_key={REDACTED}&page=2"
    assert redact("password: hunter22") == f"password: {REDACTED}"
    # o que não é credencial fica intacto
    assert redact("nmap -sV -T4 --top-ports 1000 10.0.0.5") == (
        "nmap -sV -T4 --top-ports 1000 10.0.0.5"
    )


def test_processor_redige_campos_e_chaves_mas_nao_o_nome_do_evento():
    saida = redaction_processor(
        None,
        "info",
        {
            "event": "nuclei.start_scan",
            "cmd": ["nuclei", "-H", "Cookie: sid=1"],
            "headers": {"Authorization": "Bearer xyzxyzxyz", "Accept": "*/*"},
            "api_key": "sk-123",
            "prompt_tokens": 512,
        },
    )
    assert saida == {
        "event": "nuclei.start_scan",
        "cmd": ["nuclei", "-H", REDACTED],
        "headers": {"Authorization": REDACTED, "Accept": "*/*"},
        "api_key": REDACTED,
        "prompt_tokens": 512,
    }


def test_redacao_roda_antes_do_buffer_do_sse():
    from orchestrator import main

    fonte = Path(main.__file__).read_text(encoding="utf-8")
    assert fonte.index("redaction_processor,") < fonte.index("log_processor,  #")


# ------------------------------------------------------------ rate limit (#11 a)

_P = Principal(id="op-1", email="op@x", role=Role.OPERATOR, is_service=False)


@pytest.fixture
def sem_redis(monkeypatch):
    async def fora(*_a, **_k):
        raise ConnectionError("redis fora")

    monkeypatch.setattr(ratelimit, "_contar_no_redis", fora)
    ratelimit._memoria.clear()
    monkeypatch.setattr(ratelimit.settings, "RATE_LIMIT_PER_MINUTE", 3)


async def test_passa_do_limite_e_429_com_retry_after_mesmo_sem_redis(sem_redis):
    dep = ratelimit.rate_limit("scans")
    for _ in range(3):
        await dep(principal=_P)
    with pytest.raises(HTTPException) as e:
        await dep(principal=_P)
    assert e.value.status_code == 429
    assert 0 < int(e.value.headers["Retry-After"]) <= 60


async def test_limite_e_por_principal_e_por_rota(sem_redis):
    outro = Principal(id="op-2", email="o@x", role=Role.OPERATOR, is_service=False)
    scans, investigar = ratelimit.rate_limit("scans"), ratelimit.rate_limit("investigate")
    for _ in range(3):
        await scans(principal=_P)
    await scans(principal=outro)  # outro principal, contador próprio
    await investigar(principal=_P)  # outra rota, contador próprio


async def test_zero_desliga(sem_redis, monkeypatch):
    monkeypatch.setattr(ratelimit.settings, "RATE_LIMIT_PER_MINUTE", 0)
    dep = ratelimit.rate_limit("scans")
    for _ in range(10):
        await dep(principal=_P)


def test_as_tres_rotas_caras_tem_o_limite():
    from orchestrator.api.routers import exposure, investigate, scans

    def com_limite(router) -> set[tuple[str, str]]:
        achadas = set()
        for rota in router.routes:
            nomes = {getattr(d.dependency, "__qualname__", "") for d in rota.dependencies}
            if any("rate_limit" in n for n in nomes):
                achadas |= {(m, rota.path) for m in rota.methods}
        return achadas

    assert ("POST", "/scans") in com_limite(scans.router)
    assert ("POST", "/exposure/scan") in com_limite(exposure.router)
    assert ("POST", "/investigate/{finding_id}") in com_limite(investigate.router)


# ---------------------------------------------------------------- não-root (#12)


@pytest.mark.parametrize("imagem", ["orchestrator", "kali-toolbox", "cai-expert"])
def test_imagens_terminam_em_usuario_nao_root(imagem):
    linhas = (RAIZ / "docker" / "images" / imagem / "Dockerfile").read_text().splitlines()
    usuarios = [x.split()[1] for x in linhas if x.startswith("USER ")]
    assert usuarios and usuarios[-1] == "1000"


def test_compose_de_dev_sem_capability_e_com_healthcheck():
    servicos = yaml.safe_load((RAIZ / "docker" / "compose.yml").read_text())["services"]
    for nome in ("orchestrator", "worker"):
        assert servicos[nome]["cap_drop"] == ["ALL"]
        assert "cap_add" not in servicos[nome]
    for nome in ("orchestrator", "postgres", "redis"):
        assert servicos[nome]["healthcheck"]["test"]
