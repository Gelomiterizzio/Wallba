"""DecisionEnvelope, ExecutionReceipt y estados, según docs/API_CONTRACTS.md."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from wallba.contracts.common import Identifier, Sha256Hex, StrictModel, UtcDatetime, Uuid

Decision = Literal["ALLOW", "DENY", "REQUIRE_APPROVAL"]
Risk = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ReceiptState = Literal["SUCCEEDED", "FAILED", "UNKNOWN"]
RequestState = Literal[
    "RECEIVED",
    "DENIED",
    "PENDING_APPROVAL",
    "READY",
    "EXECUTING",
    "SUCCEEDED",
    "FAILED",
    "UNKNOWN",
    "REJECTED",
    "EXPIRED",
    "CANCELLED",
]
ReasonCode = Literal[
    "RULE_ALLOW",
    "RULE_DENY",
    "DEFAULT_DENY",
    "APPROVAL_REQUIRED",
    "POLICY_MISSING",
    "POLICY_INVALID",
    "AUTHORIZATION_UNAVAILABLE",
    "SCOPE_DENIED",
    "DIGEST_MISMATCH",
    "STALE_POLICY",
    "STALE_RESOURCE",
    "APPROVAL_EXPIRED",
    "APPROVAL_ALREADY_CONSUMED",
    "AUDIT_UNAVAILABLE",
    "EXECUTION_UNKNOWN",
]


class DecisionEnvelope(StrictModel):
    request_id: Uuid
    decision: Decision
    reason_code: ReasonCode
    matched_rule_ids: list[str] = Field(max_length=100)
    policy_id: Identifier | None
    policy_version: int | None = Field(ge=1)
    risk: Risk


class ExecutionReceipt(StrictModel):
    execution_id: Uuid
    request_id: Uuid
    state: ReceiptState
    result_digest: Sha256Hex | None
    # Null significa incertidumbre, no cero efectos.
    effect_count: int | None = Field(ge=0)
    evidence_id: Uuid
    completed_at: UtcDatetime | None


class RequestView(StrictModel):
    """Vista de una solicitud de herramienta devuelta por el gateway (P3)."""

    request_id: Uuid
    state: RequestState
    decision: DecisionEnvelope | None
    approval_id: Uuid | None
    execution_id: Uuid | None
    receipt: ExecutionReceipt | None = None
