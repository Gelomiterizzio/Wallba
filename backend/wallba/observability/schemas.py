"""DTO de lectura de observabilidad. Las consultas no admiten campos desconocidos."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from wallba.contracts.common import Identifier, Sha256Hex, StrictModel, UtcDatetime, Uuid
from wallba.contracts.decision import Decision, Risk
from wallba.contracts.ports import AuditEventType
from wallba.contracts.tool_call import ToolName

MAX_EXPORT_EVENTS = 10_000
Limit = Annotated[int, Field(ge=1, le=100)]


class AuditEventView(StrictModel):
    """Evento tal como se encadenó. Un campo opcional ausente nunca se rellena."""

    schema_version: str
    event_id: Uuid
    sequence: int
    event_type: AuditEventType
    occurred_at: str
    request_id: Uuid | None = None
    run_id: Uuid | None = None
    execution_id: Uuid | None = None
    evidence_id: Uuid | None = None
    principal_id: str | None = None
    agent_id: str | None = None
    environment_id: str | None = None
    tool: ToolName | None = None
    resource_id: str | None = None
    request_digest: Sha256Hex | None = None
    decision: Decision | None = None
    risk: Risk | None = None
    policy_id: str | None = None
    policy_version: int | None = None
    reason_code: str | None = None
    checksum: Sha256Hex | None = None
    previous_hash: Sha256Hex
    event_hash: Sha256Hex


class AuditEventPage(StrictModel):
    items: list[AuditEventView]
    next_cursor: str | None


class IntegrityView(StrictModel):
    """Resultado de recalcular la cadena hasta este evento, con su límite explícito."""

    verified: bool
    checked_events: int
    first_invalid_sequence: int | None
    limitation: str


class AuditEventDetail(StrictModel):
    event: AuditEventView
    integrity: IntegrityView


class DashboardCounters(StrictModel):
    """Una denegación es una decisión, nunca una ejecución fallida."""

    events: int
    requests: int
    decisions: int
    executions_completed: int
    executions_failed: int
    executions_unknown: int
    approvals_pending: int


class DecisionCounts(StrictModel):
    ALLOW: int = 0
    DENY: int = 0
    REQUIRE_APPROVAL: int = 0


class RiskCounts(StrictModel):
    LOW: int = 0
    MEDIUM: int = 0
    HIGH: int = 0
    CRITICAL: int = 0


class DashboardView(StrictModel):
    as_of: UtcDatetime
    window_from: UtcDatetime | None
    window_to: UtcDatetime | None
    include_baseline: bool
    counters: DashboardCounters
    by_decision: DecisionCounts
    by_risk: RiskCounts
    recent: list[AuditEventView]


class AuditFilters(BaseModel):
    """`from` es inclusivo y `to` exclusivo. Solo se admiten estos campos."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    tool: ToolName | None = None
    agent_id: Identifier | None = None
    decision: Decision | None = None
    risk: Risk | None = None
    event_type: AuditEventType | None = None
    request_id: Uuid | None = None
    run_id: Uuid | None = None
    q: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    from_time: AwareDatetime | None = Field(default=None, alias="from")
    to_time: AwareDatetime | None = Field(default=None, alias="to")
    cursor: Annotated[str, Field(max_length=256)] | None = None
    limit: Limit = 50


class ExportFilters(AuditFilters):
    """La exportación exige un rango. No pagina: rechaza si supera el máximo."""

    from_time: AwareDatetime = Field(alias="from")
    to_time: AwareDatetime = Field(alias="to")
    cursor: None = None
    limit: None = None


class DashboardFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_time: AwareDatetime | None = Field(default=None, alias="from")
    to_time: AwareDatetime | None = Field(default=None, alias="to")
    include_baseline: bool = False


AuditQuery = Annotated[AuditFilters, Query()]
ExportQuery = Annotated[ExportFilters, Query()]
DashboardQuery = Annotated[DashboardFilters, Query()]
