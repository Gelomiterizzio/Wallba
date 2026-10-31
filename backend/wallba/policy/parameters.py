"""Parámetros tipados por herramienta y condiciones cerradas. Sin regex de autorización."""

from __future__ import annotations

import unicodedata
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator

from wallba.policy.models import (
    STRICT,
    IntegerConstraint,
    ParameterConditions,
    PolicyFieldError,
    StringConstraint,
    ToolName,
)
from wallba.policy.risk import QUERY_IDS

_FIELDS_BY_TOOL = {
    ToolName.FILE_READ.value: frozenset({"max_bytes"}),
    ToolName.EMAIL_SEND.value: frozenset({"to", "subject", "body"}),
    ToolName.RECORD_DELETE.value: frozenset({"record_id"}),
    ToolName.DB_QUERY.value: frozenset({"query_id", "limit"}),
}

_INTEGER_RANGES = {
    "max_bytes": (1, 16384),
    "limit": (1, 100),
}

_STRING_LIMITS = {
    "subject": 120,
    "body": 4096,
    "to": 254,
    "record_id": 36,
    "query_id": 64,
}


class ParameterRejected(Exception):
    """La solicitud no cumple el contrato de la herramienta. No es un permiso."""


class FileReadParameters(BaseModel):
    model_config = STRICT
    max_bytes: int = Field(strict=True, ge=1, le=16384)


class EmailSendParameters(BaseModel):
    model_config = STRICT
    to: str
    subject: str = Field(max_length=120)
    body: str = Field(max_length=4096)

    @field_validator("to")
    @classmethod
    def _recipient(cls, value: str) -> str:
        normalized = normalize_email(value)
        if normalized is None:
            raise ValueError("email")
        return normalized

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return _plain_text(value, allow_newline=False)

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        return _plain_text(value, allow_newline=True)


class RecordDeleteParameters(BaseModel):
    model_config = STRICT
    record_id: str

    @field_validator("record_id")
    @classmethod
    def _record(cls, value: str) -> str:
        canonical = canonical_uuid(value)
        if canonical is None:
            raise ValueError("uuid")
        return canonical


class DbQueryParameters(BaseModel):
    model_config = STRICT
    query_id: Annotated[str, Field(pattern=r"^(?:list_records|count_records)$")]
    limit: int = Field(strict=True, ge=1, le=100)


_MODELS = {
    ToolName.FILE_READ.value: FileReadParameters,
    ToolName.EMAIL_SEND.value: EmailSendParameters,
    ToolName.RECORD_DELETE.value: RecordDeleteParameters,
    ToolName.DB_QUERY.value: DbQueryParameters,
}


def normalize_email(value: object) -> str | None:
    if not isinstance(value, str) or not value.isascii():
        return None
    text = unicodedata.normalize("NFC", value).casefold()
    if len(text) < 3 or len(text) > 254:
        return None
    if any(ord(char) < 33 or ord(char) == 127 for char in text):
        return None
    if text.count("@") != 1:
        return None
    local, domain = text.split("@")
    if not _email_local(local) or not _email_domain(domain):
        return None
    return text


def canonical_uuid(value: object) -> str | None:
    if not isinstance(value, str) or not value.isascii():
        return None
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
    return str(parsed)


def _email_local(local: str) -> bool:
    if not local or local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    return all(char.isalnum() or char in "._+-" for char in local)


def _email_domain(domain: str) -> bool:
    if not domain.endswith(".test") or ".." in domain or domain.startswith(".") or domain.endswith("."):
        return False
    labels = domain.split(".")
    if len(labels) < 2:
        return False
    for label in labels:
        if not label or label.startswith("-") or label.endswith("-"):
            return False
        if not all(char.isalnum() or char == "-" for char in label):
            return False
    return True


def _plain_text(value: str, *, allow_newline: bool) -> str:
    text = unicodedata.normalize("NFC", value)
    if "\x00" in text:
        raise ValueError("control")
    for char in text:
        if ord(char) < 32 and not (allow_newline and char in "\n\t"):
            raise ValueError("control")
        if ord(char) == 127:
            raise ValueError("control")
    return text


def parse_parameters(tool: str, operation: str, payload: object) -> BaseModel:
    from wallba.policy.risk import TOOL_OPERATIONS

    if TOOL_OPERATIONS.get(tool) != operation:
        raise ParameterRejected()
    model = _MODELS.get(tool)
    if model is None or not isinstance(payload, dict):
        raise ParameterRejected()
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ParameterRejected() from exc


def validate_rule_parameters(tool_values: list[str], conditions: ParameterConditions | None) -> list[PolicyFieldError]:
    if conditions is None:
        return []
    present = [name for name in _FIELDS_BY_TOOL["file.read"] | _FIELDS_BY_TOOL["email.send"] | _FIELDS_BY_TOOL["record.delete"] | _FIELDS_BY_TOOL["db.query"] if getattr(conditions, name) is not None]
    if len(tool_values) != 1:
        return [PolicyFieldError(field="conditions.parameters", code="tool_parameter_mismatch")]
    allowed = _FIELDS_BY_TOOL[tool_values[0]]
    errors: list[PolicyFieldError] = []
    for name in present:
        if name not in allowed:
            errors.append(PolicyFieldError(field=f"conditions.parameters.{name}", code="incompatible_condition"))
            continue
        errors.extend(_constraint_errors(name, getattr(conditions, name)))
    return errors


def _constraint_errors(name: str, constraint: IntegerConstraint | StringConstraint) -> list[PolicyFieldError]:
    path = f"conditions.parameters.{name}"
    if isinstance(constraint, IntegerConstraint):
        low, high = _INTEGER_RANGES[name]
        values = [] if constraint.equals is None else [constraint.equals]
        if constraint.in_values is not None:
            values.extend(constraint.in_values)
        if any(not low <= item <= high for item in values):
            return [PolicyFieldError(field=path, code="out_of_range")]
        return []
    errors: list[PolicyFieldError] = []
    limit = _STRING_LIMITS[name]
    if constraint.max_length is not None and constraint.max_length > limit:
        errors.append(PolicyFieldError(field=f"{path}.max_length", code="out_of_range"))
    samples = [] if constraint.equals is None else [constraint.equals]
    if constraint.in_values is not None:
        samples.extend(constraint.in_values)
    for sample in samples:
        if len(sample) > limit or not _sample_allowed(name, sample):
            errors.append(PolicyFieldError(field=path, code="invalid_value"))
            break
    return errors


def _sample_allowed(name: str, sample: str) -> bool:
    if name == "to":
        normalized = normalize_email(sample)
        return normalized is not None and sample == normalized
    if name == "record_id":
        return canonical_uuid(sample) == sample
    if name == "query_id":
        return sample in QUERY_IDS
    if name in {"subject", "body"}:
        try:
            _plain_text(sample, allow_newline=(name == "body"))
        except ValueError:
            return False
        return True
    return False


def parameters_match(tool: str, parsed: BaseModel, conditions: ParameterConditions) -> bool:
    allowed = _FIELDS_BY_TOOL.get(tool)
    if allowed is None:
        raise TypeError("tool")
    for name in allowed:
        constraint = getattr(conditions, name)
        if constraint is None:
            continue
        if not hasattr(parsed, name):
            raise TypeError("parameter")
        if not _matches(name, getattr(parsed, name), constraint):
            return False
    unexpected = [
        name
        for name in (
            "max_bytes",
            "to",
            "subject",
            "body",
            "record_id",
            "query_id",
            "limit",
        )
        if getattr(conditions, name) is not None and name not in allowed
    ]
    if unexpected:
        raise TypeError("incompatible")
    return True


def _matches(name: str, actual: object, constraint: IntegerConstraint | StringConstraint) -> bool:
    if isinstance(constraint, IntegerConstraint):
        if isinstance(actual, bool) or not isinstance(actual, int):
            return False
        if constraint.equals is not None and actual != constraint.equals:
            return False
        if constraint.in_values is not None and actual not in constraint.in_values:
            return False
        return True
    if not isinstance(actual, str):
        return False
    if name == "to":
        actual_text = normalize_email(actual)
        if actual_text is None:
            return False
        return _string_match(actual_text, constraint, email=True)
    if name == "record_id":
        actual_text = canonical_uuid(actual)
        if actual_text is None:
            return False
        return _string_match(actual_text, constraint, email=False)
    return _string_match(unicodedata.normalize("NFC", actual), constraint, email=False)


def _string_match(actual: str, constraint: StringConstraint, *, email: bool) -> bool:
    def same(left: str, right: str) -> bool:
        if email:
            return left == normalize_email(right)
        return left == unicodedata.normalize("NFC", right)

    if constraint.equals is not None and not same(actual, constraint.equals):
        return False
    if constraint.in_values is not None and not any(same(actual, item) for item in constraint.in_values):
        return False
    if constraint.max_length is not None and len(actual) > constraint.max_length:
        return False
    return True
