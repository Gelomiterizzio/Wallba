"""Persona 3 tables on Persona 1's shared metadata; no teammates' models changed."""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)

from wallba.foundation.models import Base

requests = Table(
    "tool_requests",
    Base.metadata,
    Column("request_id", String(36), primary_key=True),
    Column("principal_id", ForeignKey("principals.id"), nullable=False),
    Column("principal_kind", String(8), nullable=False),
    Column("credential_hash", String(64), nullable=True),
    Column("agent_id", ForeignKey("agents.id"), nullable=False),
    Column("idempotency_key", String(36), nullable=False),
    Column("input_digest", String(64), nullable=False),
    Column("canonical_json", JSON, nullable=False),
    Column("request_digest", String(64), nullable=False),
    Column("state", String(24), nullable=False),
    Column("row_version", Integer, nullable=False),
    Column("decision_json", JSON, nullable=True),
    Column("policy_checksum", String(64), nullable=True),
    Column("demo_run_id", String(36), nullable=True),
    Column("created_at", String(40), nullable=False),
    UniqueConstraint("principal_id", "idempotency_key", name="uq_p3_idempotency"),
)
Index("ix_p3_requests_principal", requests.c.principal_id, requests.c.created_at)

executions = Table(
    "executions",
    Base.metadata,
    Column("execution_id", String(36), primary_key=True),
    Column(
        "request_id",
        ForeignKey("tool_requests.request_id"),
        nullable=False,
        unique=True,
    ),
    Column("state", String(16), nullable=False),
    Column("nonce_hash", String(64), nullable=False, unique=True),
    Column("claimed_at", String(40), nullable=False),
    Column("receipt_json", JSON, nullable=True),
    Column("reason_code", String(64), nullable=True),
    CheckConstraint(
        "state IN ('EXECUTING','SUCCEEDED','FAILED','UNKNOWN')",
        name="ck_p3_execution_state",
    ),
)

events = Table(
    "p3_audit_outbox",
    Base.metadata,
    Column("event_id", String(36), primary_key=True),
    Column("event_type", String(64), nullable=False),
    Column("request_id", String(36), nullable=True),
    Column("run_id", String(36), nullable=True),
    Column("principal_id", String(64), nullable=True),
    Column("occurred_at", String(40), nullable=False),
    Column("payload_json", JSON, nullable=False),
)
Index("ix_p3_events_request", events.c.request_id, events.c.occurred_at)
