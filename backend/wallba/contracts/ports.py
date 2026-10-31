"""Puertos compartidos. Solo firmas: sin imports de implementaciones."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from wallba.contracts.api import DemoRunView, ResourceSnapshot
from wallba.contracts.canonical import CanonicalRequest
from wallba.contracts.capability import Capability
from wallba.contracts.common import Identifier, StrictModel
from wallba.contracts.decision import DecisionEnvelope, ExecutionReceipt, RequestView
from wallba.contracts.results import ToolResult
from wallba.contracts.tool_call import ToolCall

Role = Literal["viewer", "operator", "approver", "policy_admin"]
AuditEventType = Literal[
    "request_received",
    "authorization_decided",
    "approval_created",
    "approval_approved",
    "approval_rejected",
    "approval_expired",
    "approval_cancelled",
    "execution_claimed",
    "execution_completed",
    "execution_failed",
    "execution_unknown",
    "policy_activated",
    "demo_started",
    "demo_completed",
]


class Principal(StrictModel):
    principal_id: Identifier
    kind: Literal["human", "agent"]
    roles: list[Role]


class AuditEventDraft(StrictModel):
    """Borrador sin secuencia ni hashes: los asigna el AuditSink de P4."""

    event_type: AuditEventType
    run_id: str | None = None
    principal_id: str | None = None
    request_id: str | None = None
    execution_id: str | None = None
    evidence_id: str | None = None
    agent_id: str | None = None
    environment_id: str | None = None
    tool: str | None = None
    resource_id: str | None = None
    request_digest: str | None = None
    decision: str | None = None
    risk: str | None = None
    policy_id: str | None = None
    policy_version: int | None = None
    reason_code: str | None = None
    checksum: str | None = None


class HarnessObservation(StrictModel):
    """Resultado observado de una secuencia especial (S07/S09/S10) aportada por P2/P3."""

    state: Literal["OBSERVED", "INCOMPLETE", "UNKNOWN"]
    note: str
    decisions: list[DecisionEnvelope] = []
    receipts: list[ExecutionReceipt] = []
    audit_event_ids: list[str] = []


class ScenarioHarness(Protocol):
    def observe(self, scenario_id: str, run_id: str, request_ids: list[str]) -> HarnessObservation | None:
        """Devuelve None mientras el paso humano o de control no haya ocurrido."""
        ...


class AgentAdapter(Protocol):
    def next_calls(self, scenario: str, tool_results: list[ToolResult | None]) -> list[ToolCall]: ...


class ToolGateway(Protocol):
    def submit(self, call: ToolCall, principal: Principal, idempotency_key: str) -> RequestView: ...

    def get(self, request_id: str, principal: Principal) -> RequestView: ...


class ExecutorPort(Protocol):
    def execute(self, canonical_request: CanonicalRequest, capability: Capability) -> ExecutionReceipt: ...

    def receipt(self, execution_id: str) -> ExecutionReceipt | None: ...

    def resource_version(self, resource_id: str) -> int: ...


class AuditSink(Protocol):
    def append(self, event: AuditEventDraft, transaction: Any) -> str: ...


class HumanAuthorizer(Protocol):
    """RBAC y CSRF de P3: lanza su error HTTP o devuelve el principal humano."""

    def require(self, request: Any, role: Role, *, mutation: bool) -> Principal: ...


class DemoRunner(Protocol):
    def run_pair(self, scenario_id: str, seed: int, principal: Principal) -> DemoRunView: ...


class EnvironmentPort(Protocol):
    """Preparación y observación de un entorno sintético de demo."""

    def prepare(self, run_id: str, seed: int) -> ResourceSnapshot: ...

    def snapshot(self, run_id: str) -> ResourceSnapshot: ...
