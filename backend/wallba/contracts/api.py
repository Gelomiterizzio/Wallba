"""DTO HTTP públicos de los endpoints propiedad de P1 y formato común de error."""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import Field

from wallba.contracts.common import Identifier, Sha256Hex, StrictModel, UtcDatetime, Uuid
from wallba.contracts.decision import DecisionEnvelope, ExecutionReceipt, Risk
from wallba.contracts.tool_call import ToolName

T = TypeVar("T")

ScenarioId = Literal["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10"]
DemoStatus = Literal[
    "RUNNING", "WAITING_APPROVAL", "WAITING_ADMIN_INPUT", "COMPLETED", "INCOMPLETE", "UNKNOWN"
]
SideState = Literal[
    "PENDING",
    "WAITING_APPROVAL",
    "WAITING_ADMIN_INPUT",
    "OBSERVED",
    "INCOMPLETE",
    "UNKNOWN",
    "NOT_APPLICABLE",
]
AgentRunStatus = Literal["RUNNING", "COMPLETED", "FAILED"]


class ErrorDetail(StrictModel):
    field: str
    code: str


class ErrorBody(StrictModel):
    code: str
    message: str
    request_id: Uuid
    details: list[ErrorDetail] = []


class ErrorResponse(StrictModel):
    error: ErrorBody


class Page(StrictModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


class AgentSummary(StrictModel):
    id: Identifier
    name: str
    tools: list[ToolName]
    status: Literal["ACTIVE", "DISABLED"]


class AgentDetail(AgentSummary):
    resource_scopes: list[str]
    kind_label: str


class AgentRunCreate(StrictModel):
    scenario_id: ScenarioId


class AgentRunAccepted(StrictModel):
    run_id: Uuid
    status: AgentRunStatus


class TranscriptEntry(StrictModel):
    step: int = Field(ge=0)
    intent: str
    tool: ToolName
    resource_id: str
    request_id: Uuid


class AgentRunView(StrictModel):
    run_id: Uuid
    agent_id: Identifier
    scenario_id: ScenarioId
    status: AgentRunStatus
    request_ids: list[Uuid]
    transcript: list[TranscriptEntry]
    agent_kind_label: str


class ScenarioExpectation(StrictModel):
    """Expectativa de diseño: nunca es un resultado observado."""

    label: Literal["EXPECTATION"] = "EXPECTATION"
    baseline: str
    protected: str


class ScenarioView(StrictModel):
    id: ScenarioId
    version: str
    title: str
    tool: ToolName | None
    risk: Risk | None
    expectation: ScenarioExpectation


class DemoRunCreate(StrictModel):
    scenario_id: ScenarioId
    seed: int = Field(ge=0, le=2**31 - 1)
    mode: Literal["paired"]


class DemoRunAccepted(StrictModel):
    run_id: Uuid
    status: DemoStatus


class ResourceSnapshot(StrictModel):
    state_digest: Sha256Hex
    record_count: int = Field(ge=0)
    outbox_count: int = Field(ge=0)
    journal_count: int = Field(ge=0)


class EnvironmentView(StrictModel):
    """Respuesta interna del ejecutor sobre un entorno sintético."""

    run_id: Uuid
    fixture_digest: Sha256Hex
    snapshot: ResourceSnapshot


class SideView(StrictModel):
    environment_id: Identifier
    state: SideState
    reason: str | None
    before: ResourceSnapshot | None
    after: ResourceSnapshot | None
    decisions: list[DecisionEnvelope]
    receipts: list[ExecutionReceipt]
    request_ids: list[Uuid]
    approval_ids: list[Uuid]


class DemoRunView(StrictModel):
    run_id: Uuid
    scenario_id: ScenarioId
    seed: int
    status: DemoStatus
    fixture_digest: Sha256Hex | None
    baseline: SideView
    protected: SideView
    evidence_id: Uuid | None
    started_at: UtcDatetime
    completed_at: UtcDatetime | None
    agent_kind_label: str


class EvidenceView(StrictModel):
    evidence_id: Uuid
    run_id: Uuid
    schema_version: str
    manifest: dict[str, Any]
    manifest_digest: Sha256Hex


class MatrixRow(StrictModel):
    """Fila observada: solo existe si hubo un run persistido con evidencia."""

    scenario_id: ScenarioId
    run_id: Uuid
    status: DemoStatus
    risk: Risk | None
    policy_id: Identifier | None
    policy_version: int | None
    baseline_state: SideState
    baseline_effect_count: int | None
    protected_state: SideState
    protected_decision: str | None
    protected_reason_code: str | None
    protected_effect_count: int | None
    evidence_id: Uuid
    observed_at: UtcDatetime


class HealthLive(StrictModel):
    status: Literal["ok"]


class HealthReady(StrictModel):
    database: bool
    policy: bool
    executor: bool
