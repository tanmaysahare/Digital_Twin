"""Separate the truth schema behind its own role.

T-008, AC-104.

The simulator writes ground truth. The twin must not be able to read it. If it
could, every number in the evidence pack would be worthless, and an accidental
join is exactly the kind of mistake that happens at 2 am before a deadline. The
separation is grants, not convention: the application role has no privilege on
the truth schema and no default privilege on anything created in it later.

Roles are cluster-level, so they are created only if absent. Passwords are not
set here and are never committed; a deployment sets them out of band.

Revision ID: 0002
Revises: 0001
Created: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "digitaltwin_app"
TRUTH_ROLE = "digitaltwin_truth"

CREATE_ROLE = """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
    CREATE ROLE {role} NOLOGIN;
  END IF;
END
$$;
"""


def upgrade() -> None:
    op.execute(CREATE_ROLE.format(role=APP_ROLE))
    op.execute(CREATE_ROLE.format(role=TRUTH_ROLE))

    op.execute(f"ALTER SCHEMA truth OWNER TO {TRUTH_ROLE}")
    op.execute(f"ALTER TABLE truth.scenario_injection OWNER TO {TRUTH_ROLE}")

    # The application role can work in the public schema.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        f"TO {APP_ROLE}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )

    # It has nothing at all in the truth schema. The revoke is explicit rather
    # than relying on the absence of a grant, because PUBLIC carries privileges
    # by default on objects created by a superuser.
    op.execute(f"REVOKE ALL ON SCHEMA truth FROM {APP_ROLE}")
    op.execute("REVOKE ALL ON SCHEMA truth FROM PUBLIC")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA truth FROM {APP_ROLE}")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA truth FROM PUBLIC")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {TRUTH_ROLE} IN SCHEMA truth "
        f"REVOKE ALL ON TABLES FROM {APP_ROLE}"
    )

    # The simulator's role owns the truth schema and nothing in public beyond
    # the tables it needs to emit events into.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {TRUTH_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON event TO {TRUTH_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE ALL ON TABLES FROM {APP_ROLE}"
    )
    op.execute(f"REVOKE ALL ON SCHEMA public FROM {TRUTH_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {TRUTH_ROLE}")
    op.execute("ALTER SCHEMA truth OWNER TO CURRENT_USER")
    op.execute("ALTER TABLE truth.scenario_injection OWNER TO CURRENT_USER")
    # The roles themselves are left in place. Dropping a cluster-level role that
    # another database may also use is not this migration's business.
