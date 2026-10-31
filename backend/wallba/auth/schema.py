"""Persistent auth tables registered on the shared control-plane metadata."""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
)

from wallba.foundation.models import Base

metadata = Base.metadata

principals = Table(
    "principals",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("username", String(128), unique=True, nullable=False),
    Column("password_hash", String, nullable=True),
    Column("roles_json", JSON, nullable=False),
    Column("disabled", Boolean, nullable=False),
    Column("kind", String(10), nullable=False),
    CheckConstraint("kind IN ('human','agent')", name="ck_principals_kind"),
)
sessions = Table(
    "sessions",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("principal_id", ForeignKey("principals.id"), nullable=False),
    Column("csrf_hash", String(64), nullable=False),
    Column("expires_at", String, nullable=False),
    Column("last_seen_at", String, nullable=False),
    Column("revoked_at", String, nullable=True),
)
Index("ix_sessions_principal", sessions.c.principal_id)
credentials = Table(
    "agent_credentials",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("principal_id", ForeignKey("principals.id"), nullable=False),
    Column("agent_id", ForeignKey("agents.id"), nullable=False),
    Column("scopes_json", JSON, nullable=False),
    Column("revoked_at", String, nullable=True),
)
login_limits = Table(
    "login_rate_limits",
    metadata,
    Column("subject_hash", String(64), primary_key=True),
    Column("window_start", String, nullable=False),
    Column("attempts", Integer, nullable=False),
)
