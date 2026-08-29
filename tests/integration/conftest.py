"""O engine é criado no import a partir do DATABASE_URL, então a pasta do SQLite
precisa existir antes de qualquer teste tocar o banco."""

from orchestrator.persistence.db import _ensure_sqlite_dir

_ensure_sqlite_dir()
