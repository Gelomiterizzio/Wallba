from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
)

from wallba.foundation.models import Base

approvals = Table(
    "approvals",
    Base.metadata,
    Column("approval_id", String(36), primary_key=True),
    Column(
        "request_id",
        ForeignKey("tool_requests.request_id"),
        nullable=False,
        unique=True,
    ),
    Column("status", String(16), nullable=False),
    Column("row_version", Integer, nullable=False),
    Column("snapshot_json", JSON, nullable=False),
    Column("request_digest", String(64), nullable=False),
    Column("policy_id", String(64), nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("policy_checksum", String(64), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("expires_at", String(40), nullable=False),
    Column("approver_id", ForeignKey("principals.id"), nullable=True),
    Column("reason", String(500), nullable=True),
    Column("reason_code", String(64), nullable=True),
    Column("decided_at", String(40), nullable=True),
    Column("consumed_at", String(40), nullable=True),
    CheckConstraint(
        "status IN ('PENDING','APPROVED','CONSUMED','REJECTED','EXPIRED','CANCELLED')",
        name="ck_p3_approval_state",
    ),
)
Index("ix_p3_approvals_pending", approvals.c.status, approvals.c.expires_at)
