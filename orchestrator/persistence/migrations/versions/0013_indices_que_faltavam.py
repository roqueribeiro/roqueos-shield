"""índices que os modelos declaram e as migrations nunca criaram

O `alembic check` contra um Postgres real mostrou que o schema de produção (gerado pelas
migrations) e o do standalone (gerado por `create_all` a partir dos modelos) divergiam.
Os modelos declaram `index=True` nestas colunas, e as migrations nunca criaram o índice:

- `findings.scan_id`, `findings.target_id`, `scans.target_id`, `scans.current_phase`:
  antigos (0001/0003). Em produção, listar os achados de um scan ou os scans de um alvo
  varria a tabela inteira; no standalone havia índice. Mesma consulta, custo diferente
  conforme o banco.
- `command_approvals.reference_type` e `evidence_links.papel`: das migrations 0011/0012.

Idempotente (`if_not_exists`): o standalone já tem esses índices pelo `create_all`.
O teste `tests/postgres/test_postgres_real.py::test_migrations_batem_com_os_modelos`
trava a divergência daqui para a frente.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDICES: list[tuple[str, str, str]] = [
    ("ix_findings_scan_id", "findings", "scan_id"),
    ("ix_findings_target_id", "findings", "target_id"),
    ("ix_scans_target_id", "scans", "target_id"),
    ("ix_scans_current_phase", "scans", "current_phase"),
    ("ix_command_approvals_reference_type", "command_approvals", "reference_type"),
    ("ix_evidence_links_papel", "evidence_links", "papel"),
]


def upgrade() -> None:
    for nome, tabela, coluna in _INDICES:
        op.create_index(nome, tabela, [coluna], unique=False, if_not_exists=True)


def downgrade() -> None:
    for nome, tabela, _ in reversed(_INDICES):
        op.drop_index(nome, table_name=tabela, if_exists=True)
