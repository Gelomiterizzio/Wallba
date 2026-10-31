"""Lista permitida de campos. Lo que no está aquí no llega nunca a la auditoría.

No se busca "lo sensible": cuerpos, tokens, rutas o correos no tienen campo propio, y
un valor que no encaja en el formato de su campo se redacta o se rechaza.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, get_args

from wallba.contracts.common import UUID_PATTERN
from wallba.contracts.decision import Decision, Risk
from wallba.contracts.ports import AuditEventType
from wallba.contracts.tool_call import ToolName
from wallba.observability.ports import AuditSchemaError

REDACTED = "[REDACTED]"
# Los productores de políticas nombran al actor así; el resto usa principal_id.
FIELD_ALIASES = {"actor_id": "principal_id"}

_UUID = re.compile(UUID_PATTERN)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_PRINCIPAL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_RESOURCE = re.compile(r"^[a-z]+:[a-z0-9-]{1,64}$")
_REASON = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

_ENUMS: dict[str, frozenset[str]] = {
    "tool": frozenset(get_args(ToolName)),
    "decision": frozenset(get_args(Decision)),
    "risk": frozenset(get_args(Risk)),
}
# Un valor inválido aquí es un error del productor: el evento no se escribe.
_STRICT_PATTERNS = {
    "request_id": _UUID,
    "run_id": _UUID,
    "execution_id": _UUID,
    "evidence_id": _UUID,
    "request_digest": _DIGEST,
    "checksum": _DIGEST,
}
# Un valor inválido aquí podría ser un dato que se coló: se conserva el evento sin el valor.
_REDACTED_PATTERNS = {
    "principal_id": _PRINCIPAL,
    "agent_id": _SLUG,
    "environment_id": _SLUG,
    "policy_id": _SLUG,
    "resource_id": _RESOURCE,
    "reason_code": _REASON,
}
EVENT_FIELDS = (
    *_STRICT_PATTERNS,
    *_REDACTED_PATTERNS,
    *_ENUMS,
    "policy_version",
)


def safe_event_fields(draft: Mapping[str, Any]) -> dict[str, Any]:
    """Devuelve solo campos permitidos y validados, sin los nulos."""
    event_type = draft.get("event_type")
    if event_type not in get_args(AuditEventType):
        raise AuditSchemaError("event_type")

    normalized = {FIELD_ALIASES.get(key, key): value for key, value in draft.items()}
    safe: dict[str, Any] = {"event_type": event_type}
    for field in EVENT_FIELDS:
        value = normalized.get(field)
        if value is None:
            continue
        safe[field] = _safe_value(field, value)
    return safe


def _safe_value(field: str, value: Any) -> Any:
    if field == "policy_version":
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise AuditSchemaError(field)
        return value
    if field in _ENUMS:
        if value not in _ENUMS[field]:
            raise AuditSchemaError(field)
        return value
    if field in _STRICT_PATTERNS:
        if not isinstance(value, str) or not _STRICT_PATTERNS[field].fullmatch(value):
            raise AuditSchemaError(field)
        return value
    if not isinstance(value, str) or not _REDACTED_PATTERNS[field].fullmatch(value):
        return REDACTED
    return value
