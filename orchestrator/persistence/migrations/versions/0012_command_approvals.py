"""aprovação humana por comando (Frente E)

Cria `command_approvals`: a pendência que uma pessoa aprova ou nega no modo `ask`. Ao
contrário do `audit_log` e do `evidence_snapshots`, esta tabela é MUTÁVEL de propósito —
a linha transita de `pending` para `approved`/`denied`/`expired`. A trilha imutável de
quem decidiu o quê fica no `audit_log` (eventos `command.approve`/`command.deny`).

Idempotente: o standalone cria o schema por `create_all` antes de carimbar as migrations.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "command_approvals" in set(insp.get_table_names()):
        return
    op.create_table(
        "command_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reference_type", sa.String(), nullable=False, server_default="investigation"),
        sa.Column("reference_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("command", sa.String(), nullable=False),
        sa.Column("proposed_by", sa.String(), nullable=True, index=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending", index=True),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("command_approvals")
