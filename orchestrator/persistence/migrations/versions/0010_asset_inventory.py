"""inventário de ativos entre scans (Frente A)

Cria `assets` (ativo persistente entre scans, identidade determinística em `asset_key`)
e `asset_observations` (uma linha por ativo visto num scan), e adiciona `findings.asset_id`.

A observação por scan + a cobertura do scan (`scans.scanners_ran`/`scanners_skipped`) são
o que distingue "sumiu" de "não verificado" — ver `orchestrator.domain.assets`.

Idempotente: o standalone cria o schema por `create_all` (0008) antes de carimbar as
migrations, então cada passo checa se o artefato já existe.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tabelas = set(insp.get_table_names())

    if "assets" not in tabelas:
        op.create_table(
            "assets",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("asset_key", sa.String(), nullable=False),
            sa.Column("asset_type", sa.String(), nullable=False, index=True),
            sa.Column("value", sa.String(), nullable=False, index=True),
            sa.Column("label", sa.String(), nullable=True),
            sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "last_scan_id", sa.Uuid(), sa.ForeignKey("scans.id"), nullable=True, index=True
            ),
            sa.Column("technologies", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        )
        op.create_index("ix_assets_asset_key", "assets", ["asset_key"], unique=True)

    if "asset_observations" not in tabelas:
        op.create_table(
            "asset_observations",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "asset_id", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=False, index=True
            ),
            sa.Column("scan_id", sa.Uuid(), sa.ForeignKey("scans.id"), nullable=False, index=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source_tool", sa.String(), nullable=True, index=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        )

    cols_findings = {c["name"] for c in insp.get_columns("findings")}
    if "asset_id" not in cols_findings:
        # FK nomeada: o batch_alter_table do SQLite recria a tabela e recusa constraint
        # sem nome ("Constraint must have a name").
        with op.batch_alter_table("findings") as batch:
            batch.add_column(
                sa.Column(
                    "asset_id",
                    sa.Uuid(),
                    sa.ForeignKey("assets.id", name="fk_findings_asset_id"),
                    nullable=True,
                )
            )
        op.create_index("ix_findings_asset_id", "findings", ["asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_findings_asset_id", table_name="findings")
    with op.batch_alter_table("findings") as batch:
        batch.drop_column("asset_id")
    op.drop_table("asset_observations")
    op.drop_index("ix_assets_asset_key", table_name="assets")
    op.drop_table("assets")
