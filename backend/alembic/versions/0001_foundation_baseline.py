"""Migración base P1: agents, agent_runs, demo_runs y evidence.

Revision ID: 0001_foundation
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None

ACTIVE_FILTER = "status IN ('RUNNING','WAITING_APPROVAL','WAITING_ADMIN_INPUT')"


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("tools_json", sa.JSON(), nullable=False),
        sa.Column("resource_scopes_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_agents_status"),
    )
    op.create_index("ix_agents_status", "agents", ["status"])

    op.create_table(
        "agent_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("scenario_id", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("request_ids_json", sa.JSON(), nullable=False),
        sa.Column("transcript_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('RUNNING','COMPLETED','FAILED')", name="ck_agent_runs_status"),
    )
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    op.create_table(
        "demo_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(8), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("fixture_digest", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("baseline_env", sa.String(64), nullable=False),
        sa.Column("protected_env", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "status IN ('RUNNING','WAITING_APPROVAL','WAITING_ADMIN_INPUT',"
            "'COMPLETED','INCOMPLETE','UNKNOWN')",
            name="ck_demo_runs_status",
        ),
    )
    op.create_index("ix_demo_runs_status", "demo_runs", ["status"])
    op.create_index("ix_demo_runs_scenario", "demo_runs", ["scenario_id"])
    op.execute(f"CREATE UNIQUE INDEX ux_demo_runs_single_active ON demo_runs ((1)) WHERE {ACTIVE_FILTER}")

    op.create_table(
        "evidence",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("demo_runs.run_id"), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
    )
    op.create_index("ix_evidence_run", "evidence", ["run_id"])


def downgrade() -> None:
    op.drop_table("evidence")
    op.drop_table("demo_runs")
    op.drop_table("agent_runs")
    op.drop_table("agents")
