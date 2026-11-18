"""armazém de evidência write-once (Frente C)

Cria `evidence_snapshots` (registro imutável de um corpo de evidência endereçado por
conteúdo) e `evidence_links` (vínculo achado↔evidência com papel). O `evidence_snapshots`
ganha o mesmo trigger append-only do `audit_log` (0004): em Postgres, UPDATE/DELETE são
rejeitados; o corpo é redigido antes de ser gravado pelo armazém, e a retenção apaga o
blob em disco sem tocar a linha.

Idempotente: o standalone cria o schema por `create_all` antes de carimbar as migrations.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tabelas = set(insp.get_table_names())

    if "evidence_snapshots" not in tabelas:
        op.create_table(
            "evidence_snapshots",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("sha256", sa.String(), nullable=False, index=True),
            sa.Column("original_sha256", sa.String(), nullable=False, index=True),
            sa.Column("content_type", sa.String(), nullable=False, server_default="text/plain"),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("encrypted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("scan_id", sa.Uuid(), sa.ForeignKey("scans.id"), nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        )

    if "evidence_links" not in tabelas:
        op.create_table(
            "evidence_links",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("deduped_key", sa.String(), nullable=False, index=True),
            sa.Column(
                "snapshot_id",
                sa.Uuid(),
                sa.ForeignKey("evidence_snapshots.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("papel", sa.String(), nullable=False, server_default="supporting"),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("nota", sa.String(), nullable=True),
            sa.Column("evidence_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    # Trigger append-only em evidence_snapshots (Postgres).
    # asyncpg nao aceita multi-statement: statements separados (como na 0004).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE OR REPLACE FUNCTION evidence_snapshots_immutable() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'evidence_snapshots is append-only'; END $$ LANGUAGE plpgsql"
        )
        op.execute(
            "CREATE TRIGGER evidence_snapshots_no_update "
            "BEFORE UPDATE OR DELETE ON evidence_snapshots "
            "FOR EACH ROW EXECUTE FUNCTION evidence_snapshots_immutable()"
        )


def downgrade() -> None:
    """downgrade nao suportado: evidence_snapshots guarda hashes imutáveis de evidência."""
    raise NotImplementedError(
        "downgrade nao suportado: removeria evidence_snapshots com registros imutáveis."
    )
