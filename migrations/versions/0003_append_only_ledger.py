"""Make the ledger append-only.

T-009.

The ledger is the product's evidence. A prediction that can be edited after its
outcome is known proves nothing, so the ledger is append-only in two independent
ways: a trigger that raises on UPDATE and DELETE, and an application role that
holds no UPDATE or DELETE grant on either table. Either alone would be enough;
both together mean a mistake in one does not open the other.

The outcome of a prediction is a separate row in prediction_outcome, written
once when the horizon elapses. Correcting an outcome means writing a new
prediction, not editing an old one.

Revision ID: 0003
Revises: 0002
Created: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "digitaltwin_app"
APPEND_ONLY_TABLES = ("prediction", "prediction_outcome")

TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION refuse_ledger_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION
    '% is append-only. % is not permitted on it. '
    'Write a new row instead of changing this one.',
    TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'restrict_violation';
END;
$$;
"""


def upgrade() -> None:
    op.execute(TRIGGER_FUNCTION)
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_is_append_only "
            f"BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION refuse_ledger_change()"
        )
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM {APP_ROLE}")
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_is_append_only ON {table}")
        op.execute(f"GRANT UPDATE, DELETE ON {table} TO {APP_ROLE}")
    op.execute("DROP FUNCTION IF EXISTS refuse_ledger_change()")
