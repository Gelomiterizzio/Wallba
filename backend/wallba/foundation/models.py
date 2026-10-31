"""Tablas de control propiedad de P1. Cada dominio declara las suyas sobre `Base`."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ACTIVE_DEMO_STATUSES = ("RUNNING", "WAITING_APPROVAL", "WAITING_ADMIN_INPUT")


class Base(DeclarativeBase):
    pass


class AgentRow(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_agents_status"),
        Index("ix_agents_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    tools_json: Mapped[list[str]] = mapped_column(JSON)
    resource_scopes_json: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint("status IN ('RUNNING','COMPLETED','FAILED')", name="ck_agent_runs_status"),
        Index("ix_agent_runs_status", "status"),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    scenario_id: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16))
    request_ids_json: Mapped[list[str]] = mapped_column(JSON)
    transcript_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DemoRunRow(Base):
    __tablename__ = "demo_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING','WAITING_APPROVAL','WAITING_ADMIN_INPUT',"
            "'COMPLETED','INCOMPLETE','UNKNOWN')",
            name="ck_demo_runs_status",
        ),
        Index("ix_demo_runs_status", "status"),
        Index("ix_demo_runs_scenario", "scenario_id"),
        # Un único run activo, garantizado por la base y no por memoria.
        Index(
            "ux_demo_runs_single_active",
            text("(1)"),
            unique=True,
            sqlite_where=text(
                "status IN ('RUNNING','WAITING_APPROVAL','WAITING_ADMIN_INPUT')"
            ),
        ),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(8))
    seed: Mapped[int] = mapped_column(Integer)
    fixture_digest: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    baseline_env: Mapped[str] = mapped_column(String(64))
    protected_env: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Estado parcial de ambos lados: se conserva aunque un lado falle.
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class EvidenceRow(Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_run", "run_id"),)

    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("demo_runs.run_id"))
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    manifest_digest: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(16))
