"""persiste a COBERTURA do scan: quem rodou, quem não rodou, e por quê

O pipeline já calculava `scanners_ran` e `scanners_skipped`, mas nada disso era
gravado: o `_persist_findings` escrevia state e findings e mais nada. O resultado é
que todo o trabalho de honestidade da varredura do silêncio morria no worker — a API,
a tela e o Fix Bundle continuavam mostrando "todos os scanners rodaram, zero achados".

`errors` já existia como coluna e também nunca era escrita. Aqui entram as duas
colunas estruturadas, para o bundle parar de deduzir cobertura fazendo string-parsing
de mensagem de erro.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scans") as batch:
        batch.add_column(sa.Column("scanners_ran", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(
            sa.Column("scanners_skipped", sa.JSON(), nullable=False, server_default="{}")
        )


def downgrade() -> None:
    with op.batch_alter_table("scans") as batch:
        batch.drop_column("scanners_skipped")
        batch.drop_column("scanners_ran")
