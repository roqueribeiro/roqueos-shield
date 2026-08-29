"""Tests para target_validator — gates de compliance H4 (argv injection) + H5 (SSRF)."""

from __future__ import annotations

import pytest

from orchestrator.config import settings
from orchestrator.domain.target_validator import (
    TargetValidationError,
    validate_target_value,
)

# ------------------ H4: argv injection ------------------


def test_rejects_value_starting_with_dash() -> None:
    with pytest.raises(TargetValidationError, match="injecao de flag"):
        validate_target_value("-rf /tmp", asset_type="host")


def test_rejects_value_starting_with_double_dash() -> None:
    with pytest.raises(TargetValidationError, match="injecao de flag"):
        validate_target_value("--upload-pack=evil", asset_type="repo")


def test_rejects_empty_value() -> None:
    with pytest.raises(TargetValidationError):
        validate_target_value("", asset_type="url")


# ------------------ H5: SSRF / private network ------------------


def test_rejects_imds_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    with pytest.raises(TargetValidationError, match="rede privada/loopback/IMDS"):
        validate_target_value("http://169.254.169.254/latest/meta-data/", asset_type="url")


def test_rejects_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    with pytest.raises(TargetValidationError):
        validate_target_value("http://127.0.0.1:8080/", asset_type="url")


def test_rejects_rfc1918_when_lab_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    with pytest.raises(TargetValidationError):
        validate_target_value("http://192.168.1.1/admin", asset_type="url")


def test_rejects_internal_hostnames(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    with pytest.raises(TargetValidationError):
        validate_target_value("http://localhost/admin", asset_type="url")


# ------------------ ALLOWLIST: caminho de lab ------------------


def test_allows_juice_shop_via_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "juice-shop,dvwa,webgoat")
    out = validate_target_value("http://juice-shop:3000/#/", asset_type="url")
    assert out == "http://juice-shop:3000/#/"


def test_allows_loopback_via_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "127.0.0.1")
    out = validate_target_value("http://127.0.0.1:8080/", asset_type="url")
    assert "127.0.0.1" in out


def test_allows_cidr_in_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "10.0.0.0/8")
    out = validate_target_value("http://10.5.5.5/", asset_type="url")
    assert "10.5.5.5" in out


def test_allows_wildcard_domain_in_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "*.lab.example.com")
    out = validate_target_value("http://app.lab.example.com/", asset_type="url")
    assert "app.lab.example.com" in out


def test_accepts_json_array_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tambem aceita JSON-array (compat com docs antigas)."""
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", '["juice-shop"]')
    out = validate_target_value("http://juice-shop/", asset_type="url")
    assert "juice-shop" in out


def test_public_internet_allowed_when_lab_only_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", False)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    # Sem LAB_ONLY: hosts publicos ok (operador assumiu responsabilidade)
    out = validate_target_value("https://example.com/", asset_type="url")
    assert out == "https://example.com/"


# ------------------ URL scheme + repo ------------------


def test_rejects_file_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", False)
    with pytest.raises(TargetValidationError, match="apenas http/https"):
        validate_target_value("file:///etc/passwd", asset_type="url")


def test_rejects_gopher_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", False)
    with pytest.raises(TargetValidationError, match="apenas http/https"):
        validate_target_value("gopher://example.com/", asset_type="url")


def test_rejects_repo_with_embedded_credentials() -> None:
    with pytest.raises(TargetValidationError, match="credenciais embutidas"):
        validate_target_value(
            "https://user:secrettoken@github.com/owner/repo.git", asset_type="repo"
        )


def test_accepts_ssh_repo() -> None:
    out = validate_target_value("git@github.com:owner/repo.git", asset_type="repo")
    assert out == "git@github.com:owner/repo.git"


def test_accepts_image() -> None:
    out = validate_target_value("nginx:1.27-alpine", asset_type="image")
    assert out == "nginx:1.27-alpine"


# ------------------ SEC-04: SSRF por hostname (resolve DNS) ------------------
_RESOLVE = "orchestrator.domain.target_validator._resolve_host_ips"


def test_rejects_hostname_resolving_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    monkeypatch.setattr(_RESOLVE, lambda h: ["10.0.0.5"])
    with pytest.raises(TargetValidationError, match="rede privada"):
        validate_target_value("http://postgres:5432", asset_type="url")


def test_rejects_hostname_resolving_to_imds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    monkeypatch.setattr(_RESOLVE, lambda h: ["169.254.169.254"])
    with pytest.raises(TargetValidationError):
        validate_target_value("http://metadata.attacker.example/meta", asset_type="url")


def test_allows_hostname_resolving_to_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    monkeypatch.setattr(_RESOLVE, lambda h: ["93.184.216.34"])
    assert validate_target_value("http://example.com", asset_type="url") == "http://example.com"


def test_rejects_image_registry_imds_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    with pytest.raises(TargetValidationError, match="registry"):
        validate_target_value("169.254.169.254/evil:latest", asset_type="image")


def test_host_que_nao_resolve_e_bloqueado_e_nao_liberado(monkeypatch) -> None:
    """A guarda de SSRF falhava ABERTA numa indisponibilidade de DNS.

    `_resolve_host_ips` devolve `[]` quando o DNS falha, e `any([])` é False — então
    o host passava como seguro. Defesa que se comporta como aprovação é o mesmo
    defeito de "não rodou parece não achou", com consequência pior.

    Bloquear não custa alvo legítimo: host que não resolve não seria escaneado de
    qualquer forma, e o que está na TARGET_ALLOWLIST é liberado ANTES desta checagem.
    """
    from orchestrator.domain import target_validator as tv

    monkeypatch.setattr(tv, "_resolve_host_ips", lambda h: [])
    assert tv._is_blocked_network("host-que-nao-resolve.invalid") is True


def test_host_que_resolve_para_ip_publico_continua_liberado(monkeypatch) -> None:
    from orchestrator.domain import target_validator as tv

    monkeypatch.setattr(tv, "_resolve_host_ips", lambda h: ["93.184.216.34"])
    assert tv._is_blocked_network("example.com") is False


def test_imagem_sem_registry_nao_e_tratada_como_host() -> None:
    """`nginx:1.27-alpine` não tem registry — o `:` ali é a TAG, não uma porta.

    A heurística antiga (primeiro componente com "." ou ":") tratava `nginx` como
    host de registry. Não incomodava enquanto a resolução de DNS falhava ABERTA; com
    o fail-closed, passou a recusar a imagem oficial mais comum do mundo. Registry só
    existe quando há uma barra depois do primeiro componente.
    """
    for imagem in ("nginx:1.27-alpine", "alpine:3.19", "myorg/app:2"):
        assert validate_target_value(imagem, asset_type="image") == imagem


def test_registry_em_rede_interna_continua_bloqueado() -> None:
    """O conserto acima não pode abrir o buraco do SEC-04."""
    for imagem in (
        "169.254.169.254/evil:latest",
        "127.0.0.1:5000/x:1",
        "metadata.google.internal/x:1",
    ):
        with pytest.raises(TargetValidationError, match="registry"):
            validate_target_value(imagem, asset_type="image")


@pytest.mark.parametrize(
    "repo",
    [
        "https://169.254.169.254/x/y.git",
        "http://127.0.0.1:3000/a/b.git",
        "https://postgres/x/y.git",
        "git@169.254.169.254:x/y.git",
        "git@postgres:x/y.git",
    ],
)
def test_repo_passa_pelo_guarda_de_rede(repo: str, monkeypatch) -> None:
    """`asset_type="repo"` retornava ANTES do gate H5.

    E REPO é justamente o tipo que vai direto para `git clone <target.value>` e
    `trufflehog git <target.value>` a partir do worker, dentro da rede interna. Um
    operador com `scans:run` alcançava o Gitea/GitLab interno e os serviços da rede
    do banco — e o "coração do compliance gate" não via. Medido antes do conserto:
    os cinco alvos acima eram ACEITOS, enquanto os equivalentes com `asset_type=url`
    eram recusados.
    """
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    with pytest.raises(TargetValidationError):
        validate_target_value(repo, asset_type="repo")


@pytest.mark.parametrize(
    "repo",
    [
        "https://github.com/roqueribeiro/roqueos-shield.git",
        "git@github.com:roqueribeiro/roqueos-shield.git",
    ],
)
def test_repo_publico_continua_aceito(repo: str, monkeypatch) -> None:
    """O conserto acima não pode recusar o caso normal."""
    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    assert validate_target_value(repo, asset_type="repo") == repo


def test_recusa_por_dns_nao_acusa_rede_interna(monkeypatch) -> None:
    """A mensagem afirmava o que não foi medido.

    Todo host não resolvido era acusado de estar "em rede privada/loopback/IMDS".
    Numa rede corporativa sem DNS externo — o ambiente-alvo que a própria doc
    descreve — todo alvo público legítimo seria recusado com uma acusação falsa, e o
    operador iria caçar um problema de escopo que não existe.
    """
    from orchestrator.domain import target_validator as tv

    monkeypatch.setattr(settings, "LAB_ONLY", True)
    monkeypatch.setattr(settings, "TARGET_ALLOWLIST", "")
    monkeypatch.setattr(tv, "_resolve_host_ips", lambda h: [])
    with pytest.raises(TargetValidationError, match="nao resolve em DNS"):
        validate_target_value("https://alvo-legitimo.example/", asset_type="url")
