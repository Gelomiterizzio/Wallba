"""DecisionEnvelope y ExecutionReceipt, según docs/API_CONTRACTS.md."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from wallba.contracts.common import StrictModel

Decision = Literal["ALLOW", "DENY", "REQUIRE_APPROVAL"]
Risk = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ReceiptState = Literal["SUCCEEDED", "FAILED", "UNKNOWN"]


class DecisionEnvelope(StrictModel):
    request_id: str = Field(min_length=1, max_length=64)
    decision: Decision
    reason_code: str = Field(min_length=1, max_length=64)
    matched_rule_ids: list[str] = Field(max_length=100)
    policy_id: str | None
    policy_version: int | None = Field(default=None, ge=1)
    risk: Risk


class ExecutionReceipt(StrictModel):
    execution_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=1, max_length=64)
    state: ReceiptState
    result_digest: str | None
    # UNKNOWN puede no tener conteo: null significa incertidumbre, no cero efectos.
    effect_count: int | None = Field(default=None, ge=0)
    evidence_id: str = Field(min_length=1, max_length=64)
    completed_at: datetime | None
