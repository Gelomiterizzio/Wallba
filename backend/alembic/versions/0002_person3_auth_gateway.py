"""Persona 3: auth, gateway, approvals and transactional event outbox.

Revision ID: 0002_person3
Revises: 0001_foundation
Adds only Persona 3 tables; no existing table is altered.
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_person3"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "principals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(128), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("roles_json", sa.JSON(), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.CheckConstraint("kind IN ('human','agent')", name="ck_principals_kind"),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "principal_id",
            sa.String(64),
            sa.ForeignKey("principals.id"),
            nullable=False,
        ),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.String(), nullable=False),
        sa.Column("revoked_at", sa.String(), nullable=True),
    )
    op.create_index("ix_sessions_principal", "sessions", ["principal_id"])
    op.create_table(
        "agent_credentials",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "principal_id",
            sa.String(64),
            sa.ForeignKey("principals.id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False
        ),
        sa.Column("scopes_json", sa.JSON(), nullable=False),
        sa.Column("revoked_at", sa.String(), nullable=True),
    )
    op.create_table(
        "login_rate_limits",
        sa.Column("subject_hash", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_table(
        "tool_requests",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column(
            "principal_id",
            sa.String(64),
            sa.ForeignKey("principals.id"),
            nullable=False,
        ),
        sa.Column("principal_kind", sa.String(8), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=True),
        sa.Column(
            "agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("canonical_json", sa.JSON(), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("decision_json", sa.JSON(), nullable=True),
        sa.Column("policy_checksum", sa.String(64), nullable=True),
        sa.Column("demo_run_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "principal_id", "idempotency_key", name="uq_p3_idempotency"
        ),
    )
    op.create_index(
        "ix_p3_requests_principal", "tool_requests", ["principal_id", "created_at"]
    )
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.String(36), primary_key=True),
        sa.Column(
            "request_id",
            sa.String(36),
            sa.ForeignKey("tool_requests.request_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("policy_id", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("policy_checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
        sa.Column(
            "approver_id", sa.String(64), sa.ForeignKey("principals.id"), nullable=True
        ),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("decided_at", sa.String(40), nullable=True),
        sa.Column("consumed_at", sa.String(40), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','CONSUMED','REJECTED','EXPIRED','CANCELLED')",
            name="ck_p3_approval_state",
        ),
    )
    op.create_index("ix_p3_approvals_pending", "approvals", ["status", "expires_at"])
    op.create_table(
        "executions",
        sa.Column("execution_id", sa.String(36), primary_key=True),
        sa.Column(
            "request_id",
            sa.String(36),
            sa.ForeignKey("tool_requests.request_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("claimed_at", sa.String(40), nullable=False),
        sa.Column("receipt_json", sa.JSON(), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "state IN ('EXECUTING','SUCCEEDED','FAILED','UNKNOWN')",
            name="ck_p3_execution_state",
        ),
    )
    op.create_table(
        "p3_audit_outbox",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("principal_id", sa.String(64), nullable=True),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_p3_events_request", "p3_audit_outbox", ["request_id", "occurred_at"]
    )


def downgrade():
    for name in (
        "p3_audit_outbox",
        "executions",
        "approvals",
        "tool_requests",
        "login_rate_limits",
        "agent_credentials",
        "sessions",
        "principals",
    ):
        op.drop_table(name)
