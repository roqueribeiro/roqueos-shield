"""aprovação presa ao comando exato, com consumo único (Frente E)

A aprovação valia para o approval_id, não para o comando: quem aprovava via o texto
REDIGIDO pelo scrubber (que pode esconder trecho executável, como o valor de um Cookie
ou de uma atribuição entre aspas), e a execução podia rodar outro comando, ou o mesmo
várias vezes, com a mesma aprovação.

- `command_hmac`: HMAC-SHA256 do comando original; a execução só consome a aprovação
  apresentando o mesmo comando.
- `command_enc`: o original cifrado (Fernet/SECRETS_KEY), para quem aprova ler.
- `command_redacted`: o scrubber escondeu algo? Sem original guardado, aprovar é recusado.
- status novo `consumed` (só um valor de texto: a coluna já é String).

Pendências antigas ficam com `command_hmac` nulo e nunca são consumíveis (fecha fechado).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("command_approvals")}
    with op.batch_alter_table("command_approvals") as batch:
        if "command_hmac" not in cols:
            batch.add_column(sa.Column("command_hmac", sa.String(), nullable=True))
        if "command_enc" not in cols:
            batch.add_column(sa.Column("command_enc", sa.Text(), nullable=True))
        if "command_redacted" not in cols:
            batch.add_column(
                sa.Column(
                    "command_redacted", sa.Boolean(), nullable=False, server_default=sa.false()
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("command_approvals") as batch:
        batch.drop_column("command_redacted")
        batch.drop_column("command_enc")
        batch.drop_column("command_hmac")
