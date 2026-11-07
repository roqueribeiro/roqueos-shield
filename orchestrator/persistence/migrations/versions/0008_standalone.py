"""standalone: senha do usuário e configuração editável em runtime

O RoqueShield fora do RoqueOS precisa de duas coisas que o `roqueos-server` fazia
por ele: login de gente (senha, além de token e OIDC) e um lugar para a tela gravar a
configuração de IA e de escopo sem recriar o container.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("password_hash", sa.String(), nullable=True))
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("password_hash")
