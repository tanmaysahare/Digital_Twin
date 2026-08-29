"""The simulator's ground truth tables.

T-024. AC-104.

What the line actually did: every station's real cycle time including at the six
that emit nothing, every blocked and queued second, every buffer level, and the
cause of every defect. It is the answer to the question the virtual sensors are
asked, so it lives in the truth schema, owned by the truth role, with no grant
of any kind to the application role.

The revoke is explicit rather than relying on the absence of a grant, because
PUBLIC carries privileges by default on objects created by a superuser, and a
default privilege granted in 0002 would otherwise reach a table created here.

Revision ID: 0004
Revises: 0003
Created: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "digitaltwin_app"
TRUTH_ROLE = "digitaltwin_truth"
NEW_TABLES = ("station_visit", "unit_outcome", "gate_result", "buffer_occupancy")


def upgrade() -> None:
    op.create_table(
        "station_visit",
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("station_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Text(), nullable=False),
        sa.Column("shift_id", sa.Text(), nullable=True),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("work_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("departed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cycle_time_s", sa.Numeric(), nullable=False),
        sa.Column("blocked_s", sa.Numeric(), nullable=False),
        sa.Column("queued_before_s", sa.Numeric(), nullable=False),
        sa.Column("starved_before_s", sa.Numeric(), nullable=False),
        sa.Column("down_s", sa.Numeric(), nullable=False),
        sa.Column("is_dark", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("visit_id", name="pk_station_visit"),
        schema="truth",
    )
    op.create_index(
        "ix_station_visit_run_station",
        "station_visit",
        ["run_id", "station_id"],
        schema="truth",
    )
    op.create_index(
        "ix_station_visit_run_unit",
        "station_visit",
        ["run_id", "unit_id"],
        schema="truth",
    )

    op.create_table(
        "unit_outcome",
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_id", sa.Text(), nullable=False),
        sa.Column("variant_id", sa.Text(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rework_passes", sa.Integer(), nullable=False),
        sa.Column("lots", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("run_id", "unit_id", name="pk_unit_outcome"),
        schema="truth",
    )

    op.create_table(
        "gate_result",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("gate_id", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("failure_probability", sa.Numeric(), nullable=False),
        sa.Column("defect_class", sa.Text(), nullable=True),
        sa.Column("cause_odds", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("result_id", name="pk_gate_result"),
        schema="truth",
    )
    op.create_index(
        "ix_gate_result_run_gate",
        "gate_result",
        ["run_id", "gate_id"],
        schema="truth",
    )

    op.create_table(
        "buffer_occupancy",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_id", sa.Text(), nullable=False),
        sa.Column("buffer_id", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occupancy", sa.Integer(), nullable=False),
        schema="truth",
    )
    op.create_index(
        "ix_buffer_occupancy_run_buffer",
        "buffer_occupancy",
        ["run_id", "buffer_id", "at"],
        schema="truth",
    )

    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE truth.{table} OWNER TO {TRUTH_ROLE}")
        op.execute(f"REVOKE ALL ON truth.{table} FROM {APP_ROLE}")
        op.execute(f"REVOKE ALL ON truth.{table} FROM PUBLIC")


def downgrade() -> None:
    op.drop_index(
        "ix_buffer_occupancy_run_buffer", table_name="buffer_occupancy", schema="truth"
    )
    op.drop_table("buffer_occupancy", schema="truth")
    op.drop_index("ix_gate_result_run_gate", table_name="gate_result", schema="truth")
    op.drop_table("gate_result", schema="truth")
    op.drop_table("unit_outcome", schema="truth")
    op.drop_index(
        "ix_station_visit_run_unit", table_name="station_visit", schema="truth"
    )
    op.drop_index(
        "ix_station_visit_run_station", table_name="station_visit", schema="truth"
    )
    op.drop_table("station_visit", schema="truth")
