"""Límites y validación semántica. Rechazar un documento no toca la política activa."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass

from pydantic import ValidationError

from wallba.policy.models import PolicyDocument, PolicyFieldError, PolicySnapshot
from wallba.policy.parameters import validate_rule_parameters
from wallba.policy.risk import AGENTS, ENVIRONMENTS, RESOURCES_BY_TOOL

MAX_DOCUMENT_BYTES = 64 * 1024
MAX_DEPTH = 10
MAX_RULES = 100
MAX_STRING_LENGTH = 2048
MAX_COLLECTION = 100

_PYDANTIC_CODES = {
    "extra_forbidden": "unknown_field",
    "missing": "required",
    "string_type": "type",
    "int_type": "type",
    "int_parsing": "type",
    "bool_type": "type",
    "float_type": "type",
    "list_type": "type",
    "dict_type": "type",
    "literal_error": "invalid_value",
    "enum": "invalid_value",
    "greater_than_equal": "out_of_range",
    "less_than_equal": "out_of_range",
    "too_short": "out_of_range",
    "too_long": "max_length",
    "string_pattern_mismatch": "invalid_value",
    "value_error": "invalid_value",
    "model_type": "type",
}


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    errors: tuple[PolicyFieldError, ...]
    document: PolicyDocument | None

    def normalized_policy(self) -> dict[str, object] | None:
        if self.document is None:
            return None
        return canonical_object(self.document)


def validate_mapping(data: object) -> ValidationReport:
    if not isinstance(data, dict):
        return ValidationReport(False, (PolicyFieldError(field="$", code="type"),), None)
    try:
        document = PolicyDocument.model_validate(data)
    except ValidationError as exc:
        return ValidationReport(False, tuple(_from_pydantic(exc)), None)
    errors = tuple(_semantic(document))
    if errors:
        return ValidationReport(False, errors, None)
    return ValidationReport(True, (), document)


def canonical_object(document: PolicyDocument) -> dict[str, object]:
    payload = document.model_dump(mode="json", by_alias=True, exclude_none=True)
    return _canonicalize(payload)


def canonical_bytes(document: PolicyDocument) -> bytes:
    normalized = canonical_object(document)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def document_checksum(document: PolicyDocument) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def snapshot_from_document(document: PolicyDocument) -> PolicySnapshot:
    return PolicySnapshot(document=document, checksum=document_checksum(document))


def _canonicalize(value: object) -> object:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonicalize(value[key]) for key in sorted(value)}
    raise TypeError("canonical")


def _from_pydantic(exc: ValidationError) -> list[PolicyFieldError]:
    errors: list[PolicyFieldError] = []
    for item in exc.errors():
        errors.append(
            PolicyFieldError(
                field=_location(item.get("loc", ())),
                code=_PYDANTIC_CODES.get(str(item.get("type", "")).split(".")[0], "invalid_value"),
            )
        )
    return errors or [PolicyFieldError(field="$", code="invalid_value")]


def _location(loc: object) -> str:
    if not isinstance(loc, tuple):
        return "$"
    path = ""
    for part in loc:
        name = "in" if part == "in_values" else part
        if isinstance(name, int):
            path = f"{path}[{name}]"
            continue
        text = str(name)
        path = text if not path else f"{path}.{text}"
    return path or "$"


def _semantic(document: PolicyDocument) -> list[PolicyFieldError]:
    errors: list[PolicyFieldError] = []
    seen: set[str] = set()
    for index, rule in enumerate(document.rules):
        prefix = f"rules[{index}]"
        if rule.id in seen:
            errors.append(PolicyFieldError(field=f"{prefix}.id", code="duplicate_id"))
        seen.add(rule.id)
        errors.extend(_duplicates(rule.agents, f"{prefix}.agents"))
        errors.extend(_duplicates([tool.value for tool in rule.tools], f"{prefix}.tools"))
        errors.extend(_duplicates(rule.resources, f"{prefix}.resources"))
        for agent_index, agent in enumerate(rule.agents):
            if agent not in AGENTS:
                errors.append(PolicyFieldError(field=f"{prefix}.agents[{agent_index}]", code="unknown_identifier"))
        tool_values = [tool.value for tool in rule.tools]
        allowed_resources: set[str] = set()
        for tool in tool_values:
            allowed_resources.update(RESOURCES_BY_TOOL.get(tool, frozenset()))
        for resource_index, resource in enumerate(rule.resources):
            if resource not in allowed_resources:
                errors.append(
                    PolicyFieldError(field=f"{prefix}.resources[{resource_index}]", code="unknown_identifier")
                )
        if rule.conditions is not None and rule.conditions.context_environments is not None:
            for env_index, environment in enumerate(rule.conditions.context_environments):
                if environment not in ENVIRONMENTS:
                    errors.append(
                        PolicyFieldError(
                            field=f"{prefix}.conditions.context_environments[{env_index}]",
                            code="unknown_identifier",
                        )
                    )
        relative = validate_rule_parameters(
            tool_values,
            None if rule.conditions is None else rule.conditions.parameters,
        )
        errors.extend(PolicyFieldError(field=f"{prefix}.{item.field}", code=item.code) for item in relative)
    return errors


def _duplicates(values: list[str], field: str) -> list[PolicyFieldError]:
    if len(values) != len(set(values)):
        return [PolicyFieldError(field=field, code="duplicate_item")]
    return []
