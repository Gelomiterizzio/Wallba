"""Persona 3: strict boundary using Persona 1's canonical wire contract."""

from uuid import UUID

from pydantic import ValidationError

from wallba.contracts.canonical import canonical_json, loads_strict, sha256_hex
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER
from wallba.foundation.http import ApiError


def parse_call(raw: bytes):
    if len(raw) > 65536:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "La solicitud supera el límite")
    try:
        value = loads_strict(raw)
        call = TOOL_CALL_ADAPTER.validate_python(value)
        canonical_json(call.model_dump(mode="json"))
        return call
    except (
        ValueError,
        TypeError,
        ValidationError,
        UnicodeError,
        RecursionError,
    ) as exc:
        raise ApiError(
            422, "VALIDATION_ERROR", "La solicitud no cumple el contrato"
        ) from exc


def idempotency_key(value: str):
    try:
        if not isinstance(value, str) or len(value) != 36:
            raise ValueError()
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ApiError(
            422, "VALIDATION_ERROR", "Idempotency-Key debe ser un UUID"
        ) from exc


def input_digest(call):
    # This hash is stable when resource versions change after a completed effect.
    # The execution digest separately includes server-derived context/version.
    return sha256_hex(canonical_json(call.model_dump(mode="json")))
