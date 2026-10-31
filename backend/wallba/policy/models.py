"""Modelos de dominio del motor de políticas. Validación estricta, sin coerción."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STRICT = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

SLUG = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
RESOURCE_ID = r"^(?:file|mailbox|table|query):[a-z0-9]+(?:-[a-z0-9]+)*$"
TOKEN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
ROLE_NAME = r"^(?:viewer|operator|approver|policy_admin|agent)$"

NIL_REQUEST_ID = "00000000-0000-0000-0000-000000000000"
MAX_VERSION = 1_000_000


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class Risk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReasonCode(str, Enum):
    RULE_ALLOW = "RULE_ALLOW"
    RULE_DENY = "RULE_DENY"
    DEFAULT_DENY = "DEFAULT_DENY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    POLICY_MISSING = "POLICY_MISSING"
    POLICY_INVALID = "POLICY_INVALID"
    AUTHORIZATION_UNAVAILABLE = "AUTHORIZATION_UNAVAILABLE"
    SCOPE_DENIED = "SCOPE_DENIED"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    STALE_POLICY = "STALE_POLICY"
    STALE_RESOURCE = "STALE_RESOURCE"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_ALREADY_CONSUMED = "APPROVAL_ALREADY_CONSUMED"
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"
    EXECUTION_UNKNOWN = "EXECUTION_UNKNOWN"


class ToolName(str, Enum):
    FILE_READ = "file.read"
    EMAIL_SEND = "email.send"
    RECORD_DELETE = "record.delete"
    DB_QUERY = "db.query"


class PolicyFieldError(BaseModel):
    """Detalle seguro: ruta y código, nunca el valor rechazado."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    field: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=1, max_length=64)


def _uuid_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("type")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("invalid_value") from exc
    return str(parsed)


class IntegerConstraint(BaseModel):
    model_config = STRICT
    equals: int | None = Field(default=None, strict=True)
    in_values: list[Annotated[int, Field(strict=True)]] | None = Field(
        default=None, alias="in", min_length=1, max_length=100
    )

    @model_validator(mode="after")
    def _has_operator(self) -> IntegerConstraint:
        if self.equals is None and self.in_values is None:
            raise ValueError("empty")
        if isinstance(self.equals, bool):
            raise ValueError("type")
        if self.in_values is not None and any(isinstance(item, bool) for item in self.in_values):
            raise ValueError("type")
        return self


class StringConstraint(BaseModel):
    model_config = STRICT
    equals: str | None = Field(default=None, max_length=2048)
    in_values: list[Annotated[str, Field(max_length=2048)]] | None = Field(
        default=None, alias="in", min_length=1, max_length=100
    )
    max_length: int | None = Field(default=None, strict=True, ge=1, le=4096)

    @model_validator(mode="after")
    def _has_operator(self) -> StringConstraint:
        if self.equals is None and self.in_values is None and self.max_length is None:
            raise ValueError("empty")
        return self


class ParameterConditions(BaseModel):
    model_config = STRICT
    max_bytes: IntegerConstraint | None = None
    to: StringConstraint | None = None
    subject: StringConstraint | None = None
    body: StringConstraint | None = None
    record_id: StringConstraint | None = None
    query_id: StringConstraint | None = None
    limit: IntegerConstraint | None = None

    @model_validator(mode="after")
    def _non_empty(self) -> ParameterConditions:
        if all(getattr(self, name) is None for name in _PARAMETER_FIELDS):
            raise ValueError("empty")
        return self


_PARAMETER_FIELDS = (
    "max_bytes",
    "to",
    "subject",
    "body",
    "record_id",
    "query_id",
    "limit",
)


class Conditions(BaseModel):
    model_config = STRICT
    principal_roles: list[Annotated[str, Field(pattern=ROLE_NAME)]] | None = Field(
        default=None, min_length=1, max_length=100
    )
    context_environments: list[Annotated[str, Field(pattern=SLUG, max_length=64)]] | None = Field(
        default=None, min_length=1, max_length=100
    )
    risk_at_most: Literal["LOW", "MEDIUM", "HIGH"] | None = None
    parameters: ParameterConditions | None = None

    @model_validator(mode="after")
    def _non_empty(self) -> Conditions:
        if (
            self.principal_roles is None
            and self.context_environments is None
            and self.risk_at_most is None
            and self.parameters is None
        ):
            raise ValueError("empty")
        return self


class Rule(BaseModel):
    model_config = STRICT
    id: str = Field(pattern=SLUG, min_length=1, max_length=64)
    effect: Decision
    agents: list[Annotated[str, Field(pattern=SLUG, max_length=64)]] = Field(min_length=1, max_length=100)
    tools: list[ToolName] = Field(min_length=1, max_length=100)
    resources: list[Annotated[str, Field(pattern=RESOURCE_ID, max_length=128)]] = Field(
        min_length=1, max_length=100
    )
    conditions: Conditions | None = None


class PolicyDocument(BaseModel):
    model_config = STRICT
    schema_version: Literal["1"]
    policy_id: str = Field(pattern=SLUG, min_length=1, max_length=64)
    version: int = Field(strict=True, ge=1, le=MAX_VERSION)
    rules: list[Rule] = Field(min_length=1, max_length=100)


class PolicySnapshot(BaseModel):
    model_config = STRICT
    document: PolicyDocument
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvaluationRequest(BaseModel):
    model_config = STRICT
    request_id: str
    agent_id: str = Field(pattern=SLUG, min_length=1, max_length=64)
    tool: ToolName
    operation: Literal["read", "send", "delete", "query"]
    resource_id: str = Field(pattern=RESOURCE_ID, min_length=1, max_length=128)
    parameters: dict[str, Any]

    @field_validator("request_id")
    @classmethod
    def _request_id(cls, value: str) -> str:
        return _uuid_text(value)

    @field_validator("parameters")
    @classmethod
    def _parameters_are_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 16:
            raise ValueError("out_of_range")
        return value


class TrustedContext(BaseModel):
    """Contexto inyectado por el gateway. No se lee del texto del agente."""

    model_config = STRICT
    principal_id: str = Field(pattern=TOKEN, min_length=1, max_length=128)
    agent_id: str = Field(pattern=SLUG, min_length=1, max_length=64)
    roles: list[Annotated[str, Field(pattern=ROLE_NAME)]] = Field(min_length=0, max_length=100)
    environment_id: str = Field(pattern=SLUG, min_length=1, max_length=64)
    server_time: datetime
    resource_version: str = Field(pattern=TOKEN, min_length=1, max_length=128)
    risk: Risk | None = None

    @field_validator("server_time")
    @classmethod
    def _aware_clock(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("naive_clock")
        return value


class DecisionResult(BaseModel):
    model_config = STRICT
    request_id: str
    decision: Decision
    reason_code: ReasonCode
    matched_rule_ids: list[Annotated[str, Field(pattern=SLUG, max_length=64)]] = Field(max_length=100)
    policy_id: str | None = Field(default=None, pattern=SLUG, max_length=64)
    policy_version: int | None = Field(default=None, strict=True, ge=1, le=MAX_VERSION)
    risk: Risk

    @field_validator("request_id")
    @classmethod
    def _request_id(cls, value: str) -> str:
        return _uuid_text(value)

    @model_validator(mode="after")
    def _consistent(self) -> DecisionResult:
        if list(self.matched_rule_ids) != sorted(self.matched_rule_ids):
            raise ValueError("unsorted")
        if self.risk is Risk.CRITICAL and self.decision is not Decision.DENY:
            raise ValueError("critical")
        allow_reasons = {ReasonCode.RULE_ALLOW}
        approval_reasons = {ReasonCode.APPROVAL_REQUIRED}
        if self.decision is Decision.ALLOW and self.reason_code not in allow_reasons:
            raise ValueError("reason")
        if self.decision is Decision.REQUIRE_APPROVAL and self.reason_code not in approval_reasons:
            raise ValueError("reason")
        if self.decision is Decision.DENY and self.reason_code in allow_reasons | approval_reasons:
            raise ValueError("reason")
        return self
