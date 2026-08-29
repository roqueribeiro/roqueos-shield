"""Configuração da suíte.

O banco de teste é ISOLADO da máquina. Antes disto, a suíte usava o SQLite de dev
(`./data/cai.db`) que `init_db()` cria com `create_all` — e `create_all` não faz
ALTER. Consequência prática: quem já tinha rodado o projeto ficava com um arquivo de
schema antigo, e um teste passava ou falhava dependendo do histórico da máquina, não
do código. Foi assim que a migration 0007 quebrou um cenário que não tinha nada a ver
com ela.

Um banco novo por sessão de teste tira essa variável: o que a suíte afirma é sobre o
schema atual, sempre.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="session")
def _banco_isolado() -> object:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel.ext.asyncio.session import AsyncSession

    from orchestrator.config import settings
    from orchestrator.persistence import db as dbmod

    tmp = tempfile.TemporaryDirectory(prefix="cai-tests-")
    caminho = Path(tmp.name) / "test.db"
    url = f"sqlite+aiosqlite:///{caminho}"

    engine = create_async_engine(url)
    fabrica = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    antigo_engine, antiga_fabrica = dbmod._engine, dbmod._session_factory
    antiga_url = settings.DATABASE_URL
    dbmod._engine, dbmod._session_factory = engine, fabrica
    settings.DATABASE_URL = url
    try:
        yield
    finally:
        dbmod._engine, dbmod._session_factory = antigo_engine, antiga_fabrica
        settings.DATABASE_URL = antiga_url
        tmp.cleanup()
