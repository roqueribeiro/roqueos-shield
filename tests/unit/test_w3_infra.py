"""Infra de dev e prod: compose, Makefile e comandos do Claude dizem a verdade.

Lê os arquivos como estão (YAML cru, `make -n`), sem Docker. Cada teste fecha um
defeito que existiu: chave do ZAP e senha do Redis na linha de comando, Ollama com
GPU no profile default, `make down` que não descia Greenbone e Caddy, `make test`
rodando numa imagem sem testes, comandos sem `--project-directory docker`.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[2]
DOCKER = RAIZ / "docker"
COMPOSES = sorted(DOCKER.glob("compose*.yml"))


def _carregar(nome: str) -> dict[str, Any]:
    return yaml.safe_load((DOCKER / nome).read_text(encoding="utf-8"))


def _argv(svc: dict[str, Any]) -> list[str]:
    partes: list[str] = []
    for chave in ("entrypoint", "command"):
        v = svc.get(chave)
        if isinstance(v, str):
            partes.append(v)
        elif isinstance(v, list):
            partes += [str(x) for x in v]
    return partes


# --- segredo fora da linha de comando --------------------------------------------


@pytest.mark.parametrize("arquivo", COMPOSES, ids=lambda p: p.name)
def test_nenhum_segredo_na_linha_de_comando(arquivo: Path) -> None:
    dados = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
    for nome, svc in (dados.get("services") or {}).items():
        for parte in _argv(svc):
            # Dentro de um script `sh -c`, só vale o que chega ao exec final.
            assert "api.key=$" not in parte.replace("api.key=%s", ""), nome
            assert "--requirepass" not in parte, nome
            assert not re.search(r"-config\s+api\.key=", parte), nome


def _script(nome_arquivo: str, servico: str, chave: str) -> str:
    svc = _carregar(nome_arquivo)["services"][servico]
    corpo = svc[chave][2]
    # `$$` é escape do compose; no container o sh recebe `$`.
    return corpo.replace("$$", "$")


@pytest.fixture
def binarios_falsos(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sonda = (
        "#!/bin/sh\n"
        'printf "ARGV=%s\\n" "$*"\n'
        'printf "ENV_ZAP=%s\\n" "${ZAP_API_KEY:-<vazio>}"\n'
        'printf "ENV_REDIS=%s\\n" "${REDIS_PASSWORD:-<vazio>}"\n'
    )
    for nome in ("zap.sh", "redis-server"):
        p = bin_dir / nome
        p.write_text(sonda)
        p.chmod(0o755)
    return bin_dir


def _rodar(
    script: str, bin_dir: Path, home: Path, *args: str, **env: str
) -> subprocess.CompletedProcess[str]:
    ambiente = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(home), **env}
    return subprocess.run(
        ["sh", "-c", script, "entrypoint", *args],
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _zap(arquivo: str) -> tuple[str, list[str]]:
    svc = _carregar(arquivo)["services"]["zap"]
    return _script(arquivo, "zap", "entrypoint"), [str(x) for x in svc["command"]]


@pytest.mark.skipif(shutil.which("sh") is None, reason="sem sh")
@pytest.mark.parametrize("arquivo", ["compose.scanners.yml", "compose.prod.yml"])
def test_zap_recebe_a_chave_por_arquivo_0600(
    arquivo: str, binarios_falsos: Path, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    script, cmd = _zap(arquivo)
    r = _rodar(script, binarios_falsos, home, *cmd, ZAP_API_KEY="chave-de-teste")
    assert r.returncode == 0, r.stderr
    assert "chave-de-teste" not in r.stdout  # nem no argv, nem no ambiente do java
    assert "ENV_ZAP=<vazio>" in r.stdout
    assert "-configfile" in r.stdout
    assert "-daemon" in r.stdout and "-port 8090" in r.stdout
    arq = home / "zap-api.properties"
    assert stat.S_IMODE(arq.stat().st_mode) == 0o600
    texto = arq.read_text()
    assert "api.key=chave-de-teste" in texto
    assert "api.disablekey=false" in texto


@pytest.mark.parametrize("arquivo", ["compose.scanners.yml", "compose.prod.yml"])
def test_zap_sem_chave_nao_sobe(arquivo: str, binarios_falsos: Path, tmp_path: Path) -> None:
    script, cmd = _zap(arquivo)
    r = _rodar(script, binarios_falsos, tmp_path, *cmd, ZAP_API_KEY="")
    assert r.returncode != 0
    assert "ARGV=" not in r.stdout


def test_redis_prod_recebe_a_senha_por_arquivo(binarios_falsos: Path, tmp_path: Path) -> None:
    conf = tmp_path / "redis-auth.conf"
    script = _script("compose.prod.yml", "redis", "command").replace(
        "/tmp/redis-auth.conf",  # noqa: S108  o caminho do compose, trocado por tmp_path
        str(conf),
    )
    r = _rodar(script, binarios_falsos, tmp_path, REDIS_PASSWORD="senha-de-teste")  # noqa: S106
    assert r.returncode == 0, r.stderr
    assert "senha-de-teste" not in r.stdout
    assert "ENV_REDIS=<vazio>" in r.stdout
    assert stat.S_IMODE(conf.stat().st_mode) == 0o600
    assert conf.read_text() == "requirepass senha-de-teste\n"


# --- endurecimento (Issue #12) -----------------------------------------------------


def _tmpfs(svc: dict[str, Any]) -> set[str]:
    alvos = {str(t).split(":", 1)[0] for t in svc.get("tmpfs") or []}
    for v in svc.get("volumes") or []:
        if isinstance(v, dict) and v.get("type") == "tmpfs":
            alvos.add(v["target"])
    return alvos


@pytest.mark.parametrize(
    ("arquivo", "servico"),
    [
        ("compose.yml", "orchestrator"),
        ("compose.yml", "worker"),
        ("compose.prod.yml", "shield"),
        ("compose.prod.yml", "worker"),
    ],
)
def test_raiz_so_de_leitura_com_tmp_gravavel(arquivo: str, servico: str) -> None:
    svc = _carregar(arquivo)["services"][servico]
    assert svc.get("read_only") is True
    assert "/tmp" in _tmpfs(svc)  # noqa: S108  o alvo do tmpfs no compose
    assert svc.get("cap_drop") == ["ALL"]
    assert "no-new-privileges:true" in svc.get("security_opt", [])
    assert "cap_add" not in svc  # nmap faz connect scan: NET_RAW não volta


@pytest.mark.parametrize(
    ("arquivo", "servico"),
    [
        ("compose.yml", "orchestrator"),
        ("compose.scanners.yml", "zap"),
        ("compose.prod.yml", "shield"),
        ("compose.prod.yml", "zap"),
    ],
)
def test_healthcheck(arquivo: str, servico: str) -> None:
    hc = _carregar(arquivo)["services"][servico].get("healthcheck") or {}
    assert hc.get("test") and not hc.get("disable")
    # Healthcheck não carrega segredo.
    assert "apikey" not in " ".join(map(str, hc["test"]))


def test_ollama_fora_do_default() -> None:
    servicos = _carregar("compose.yml")["services"]
    assert servicos["ollama"]["profiles"] == ["ollama"]
    for nome, svc in servicos.items():
        reserva = (svc.get("deploy") or {}).get("resources", {}).get("reservations", {})
        if reserva.get("devices"):
            assert "default" not in svc.get("profiles", []), nome


def test_gsa_e_http() -> None:
    gsa = [p for p in _carregar("compose.greenbone.yml")["services"]["greenbone-gsa"]["ports"]]
    assert any(str(p).endswith(":9392:80") for p in gsa)
    arquivos = [
        RAIZ / "Makefile",
        *COMPOSES,
        RAIZ / "docs" / "OPERATIONS.md",
        RAIZ / "docs" / "DEVELOPMENT.md",
        RAIZ / "docs" / "pt-BR" / "OPERACAO.md",
        RAIZ / "docs" / "pt-BR" / "DESENVOLVIMENTO.md",
    ]
    for a in arquivos:
        assert "https://127.0.0.1:9392" not in a.read_text(encoding="utf-8"), a.name


# --- Makefile ------------------------------------------------------------------------


def _make_n(*alvos: str) -> str:
    r = subprocess.run(
        ["make", "-n", "-C", str(RAIZ), *alvos],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.mark.skipif(shutil.which("make") is None, reason="sem make")
@pytest.mark.parametrize("alvo", ["down", "clean"])
def test_down_e_clean_cobrem_todos_os_arquivos_e_profiles(alvo: str) -> None:
    saida = _make_n(alvo)
    profiles: set[str] = set()
    for arquivo in COMPOSES:
        if arquivo.name == "compose.prod.yml":  # outro projeto (roqueshield)
            continue
        assert f"-f docker/{arquivo.name}" in saida, arquivo.name
        dados = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
        for svc in (dados.get("services") or {}).values():
            profiles.update(svc.get("profiles") or [])
    for p in profiles:
        assert f"--profile {p}" in saida, p


@pytest.mark.skipif(shutil.which("make") is None, reason="sem make")
@pytest.mark.parametrize("alvo", ["test", "lint", "typecheck"])
def test_test_e_lint_rodam_no_checkout(alvo: str) -> None:
    saida = _make_n(alvo)
    assert "docker" not in saida
    assert "uv run" in saida


@pytest.mark.skipif(shutil.which("make") is None, reason="sem make")
@pytest.mark.parametrize("alvo", ["scan", "scan-no-ai", "exposure"])
def test_cli_troca_o_entrypoint_uvicorn(alvo: str) -> None:
    saida = _make_n(alvo)
    assert "--entrypoint python orchestrator -m orchestrator.cli" in saida


# --- comandos do Claude ----------------------------------------------------------------


def test_comandos_passam_env_file_e_project_directory() -> None:
    for arquivo in sorted((RAIZ / ".claude" / "commands").glob("*.md")):
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if "docker compose" in linha and "-f docker/" in linha:
                assert "--env-file .env" in linha, f"{arquivo.name}: {linha}"
                assert "--project-directory docker" in linha, f"{arquivo.name}: {linha}"


def test_comandos_nao_poem_segredo_em_tela_ou_argv() -> None:
    for arquivo in sorted((RAIZ / ".claude" / "commands").glob("*.md")):
        texto = arquivo.read_text(encoding="utf-8")
        assert "apikey=$" not in texto, arquivo.name
        assert "token=${TOKEN}" not in texto, arquivo.name
        assert "run --rm --entrypoint pytest orchestrator" not in texto, arquivo.name
