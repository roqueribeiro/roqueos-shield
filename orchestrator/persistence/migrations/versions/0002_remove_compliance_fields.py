"""remove compliance fields and audit_log

Drop audit_log table and trigger; drop authorization_ref from scans;
drop contains_pci from targets. contains_pii MANTÉM (boa prática genérica).

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-29

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Drop trigger e function (Postgres). asyncpg não aceita multi-statement —
    # statements separados.
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log")
        op.execute("DROP FUNCTION IF EXISTS audit_log_immutable")

    # 2. Drop tabela audit_log (depende dos índices)
    op.drop_table("audit_log")

    # 3. Drop colunas regulatórias
    # O índice PRIMEIRO. Em SQLite o `batch_alter_table` recria a tabela e reflete os
    # índices existentes — incluindo o `ix_scans_authorization_ref`, que a 0001 cria
    # junto com a coluna. Resultado medido num SQLite limpo:
    #   sqlite3.OperationalError: no such column: authorization_ref
    #   [SQL: CREATE INDEX ix_scans_authorization_ref ON scans (authorization_ref)]
    # `alembic upgrade head` morria na 0002 e NUNCA chegava nas migrations seguintes
    # — inclusive a 0004, que é quem cria o trigger append-only da trilha imutável.
    # Postgres não sofria (DROP COLUMN derruba o índice sozinho), e SQLite é o
    # DATABASE_URL default. Ninguém via porque nenhum teste rodava alembic.
    with op.batch_alter_table("scans") as batch:
        batch.drop_index("ix_scans_authorization_ref")
        batch.drop_column("authorization_ref")
    with op.batch_alter_table("targets") as batch:
        batch.drop_column("contains_pci")
    # contains_pii MANTÉM — útil pra rotear AI triage ao backend local.


def downgrade() -> None:
    raise NotImplementedError("downgrade não suportado: dados de audit_log perdidos no upgrade.")
