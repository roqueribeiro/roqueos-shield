"""Onde o código enviado espera o scan: `DATA_DIR/code/<upload_id>.tar.gz` + metadados.

O tarball fica no disco compartilhado entre a API (que recebe) e o worker (que extrai
e escaneia). É de uso único: o worker apaga quando o scan termina, dê certo ou não. O
que nunca foi escaneado sai no expurgo diário depois de `CODE_UPLOAD_TTL_HOURS`. Código
de cliente não fica parado no disco do scanner.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import structlog

from orchestrator.config import settings

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Envio:
    upload_id: str
    projeto: str
    sha256: str
    bytes_comprimidos: int
    arquivos: int
    bytes_descomprimidos: int
    criado_em: str
    actor: str

    @property
    def expira_em(self) -> datetime:
        return datetime.fromisoformat(self.criado_em) + timedelta(
            hours=settings.CODE_UPLOAD_TTL_HOURS
        )


def pasta() -> Path:
    p = Path(settings.DATA_DIR) / "code"
    p.mkdir(parents=True, exist_ok=True)
    return p


def tarball(upload_id: UUID | str) -> Path:
    return pasta() / f"{UUID(str(upload_id))}.tar.gz"


def _meta(upload_id: UUID | str) -> Path:
    return pasta() / f"{UUID(str(upload_id))}.json"


def gravar_meta(envio: Envio) -> None:
    _meta(envio.upload_id).write_text(json.dumps(asdict(envio)), encoding="utf-8")


def ler(upload_id: UUID | str) -> Envio | None:
    """O envio, ou None se não existe (nunca existiu, já foi usado ou expirou)."""
    m = _meta(upload_id)
    if not m.exists() or not tarball(upload_id).exists():
        return None
    return Envio(**json.loads(m.read_text(encoding="utf-8")))


def apagar(upload_id: UUID | str) -> None:
    for p in (tarball(upload_id), _meta(upload_id)):
        p.unlink(missing_ok=True)


def expurgar_vencidos(agora: datetime | None = None) -> list[str]:
    """Apaga envios que passaram do prazo sem scan. Devolve os ids apagados."""
    agora = agora or datetime.now(UTC)
    apagados: list[str] = []
    for m in pasta().glob("*.json"):
        try:
            envio = Envio(**json.loads(m.read_text(encoding="utf-8")))
        except (ValueError, TypeError) as e:
            # Metadado ilegível não pode deixar código esquecido no disco: sai também.
            log.warning("codigo.meta_ilegivel", arquivo=m.name, erro=str(e))
            m.with_name(m.stem + ".tar.gz").unlink(missing_ok=True)
            m.unlink(missing_ok=True)
            apagados.append(m.stem)
            continue
        if envio.expira_em <= agora:
            apagar(envio.upload_id)
            apagados.append(envio.upload_id)
    # Tarball sem metadado (gravação interrompida) também é lixo.
    for t in pasta().glob("*.tar.gz"):
        if not t.with_name(t.name.removesuffix(".tar.gz") + ".json").exists():
            t.unlink(missing_ok=True)
            apagados.append(t.name.removesuffix(".tar.gz"))
    return apagados
