"""Acesso à API do shield, com a credencial de quem chama.

Ordem da configuração: variável de ambiente (`ROQUESHIELD_URL`, `ROQUESHIELD_TOKEN`,
o caso do CI), depois o arquivo que o `roqueshield login` grava
(`~/.config/roqueshield/config.json`, 0600). O token nunca é impresso.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


def arquivo_de_config() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "roqueshield" / "config.json"


@dataclass(frozen=True)
class Config:
    servidor: str
    token: str


class SemConfig(RuntimeError):
    pass


class ErroDaApi(RuntimeError):
    def __init__(self, status: int, detalhe: Any) -> None:
        super().__init__(f"HTTP {status}: {detalhe}")
        self.status = status
        self.detalhe = detalhe


def carregar(env: dict[str, str] | None = None) -> Config:
    e = os.environ if env is None else env
    arq = arquivo_de_config()
    salvo: dict[str, str] = {}
    if arq.exists():
        salvo = json.loads(arq.read_text(encoding="utf-8"))
    servidor = e.get("ROQUESHIELD_URL") or salvo.get("server", "")
    token = e.get("ROQUESHIELD_TOKEN") or salvo.get("token", "")
    if not servidor or not token:
        raise SemConfig(
            "sem servidor ou token: rode `roqueshield login --server URL`, "
            "ou defina ROQUESHIELD_URL e ROQUESHIELD_TOKEN"
        )
    return Config(servidor.rstrip("/"), token)


def salvar(cfg: Config) -> Path:
    arq = arquivo_de_config()
    arq.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(arq.parent, 0o700)
    tmp = arq.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"server": cfg.servidor, "token": cfg.token}, f)
    tmp.replace(arq)
    return arq


class Api:
    def __init__(self, cfg: Config, cliente: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self.http = (
            cliente if cliente is not None else httpx.Client(base_url=cfg.servidor, timeout=30)
        )
        self.http.headers["X-API-Token"] = cfg.token

    def _req(self, metodo: str, caminho: str, **kw: Any) -> Any:
        r = self.http.request(metodo, caminho, **kw)
        if r.status_code >= 400:
            try:
                detalhe = r.json().get("detail")
            except Exception:  # noqa: BLE001
                detalhe = r.text[:300]
            raise ErroDaApi(r.status_code, detalhe)
        if r.status_code == 204:
            return None
        if "json" in r.headers.get("content-type", ""):
            return r.json()
        return r.text

    def get(self, caminho: str, **kw: Any) -> Any:
        return self._req("GET", caminho, **kw)

    def post(self, caminho: str, corpo: Any = None) -> Any:
        return self._req("POST", caminho, json=corpo or {})

    def put(self, caminho: str, corpo: Any = None) -> Any:
        return self._req("PUT", caminho, json=corpo or {})

    def delete(self, caminho: str) -> Any:
        return self._req("DELETE", caminho)
