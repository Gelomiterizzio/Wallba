"""Auditoría de P4: eventos encadenados y append-only a nivel de base.

Revision ID: 0004_audit
Revises: 0003_policy
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_audit"
down_revision = "0003_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("sequence", sa.Integer(), nullable=False, unique=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.String(20), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("execution_id", sa.String(36), nullable=True),
        sa.Column("principal_id", sa.String(128), nullable=True),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("environment_id", sa.String(64), nullable=True),
        sa.Column("tool", sa.String(32), nullable=True),
        sa.Column("decision", sa.String(24), nullable=True),
        sa.Column("risk", sa.String(16), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=True),
        # Bytes exactos que se encadenaron; las columnas anteriores solo sirven para filtrar.
        sa.Column("fields_json", sa.Text(), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_audit_request", "audit_events", ["request_id"])
    op.create_index("ix_audit_run", "audit_events", ["run_id"])
    op.create_index("ix_audit_time", "audit_events", ["occurred_at", "event_id"])
    op.create_index("ix_audit_dimensions", "audit_events", ["agent_id", "tool", "decision"])
    op.execute(
        "CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit_events es append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events "
        "BEGIN SELECT RAISE(ABORT, 'audit_events es append-only'); END"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_events_no_delete")
    op.execute("DROP TRIGGER audit_events_no_update")
    op.drop_table("audit_events")
