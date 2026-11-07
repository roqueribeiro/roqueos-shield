"""versão da sessão do usuário

`users.session_version` sobe no logout, na troca de senha e na desativação, e o JWT de
sessão emitido antes deixa de valer. Sem isto o JWT valia até expirar, mesmo depois de
sair ou de trocar a senha por suspeita de vazamento.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotente: um SQLite criado pelo `create_all` já com a coluna é carimbado na
    # base do standalone (0008) pelo supervisor e passa por aqui.
    colunas = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    if "session_version" in colunas:
        return
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("session_version", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("session_version")
