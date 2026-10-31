"""JSON canónico y digest definidos en docs/INTEGRATION_CONTRACTS.md.

UTF-8, claves ordenadas recursivamente, sin whitespace, strings NFC y solo
strings/bools/enteros/listas/objetos/null. No es RFC 8785.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import Field

from wallba.contracts.common import Identifier, StrictModel, ensure_nfc
from wallba.contracts.tool_call import ToolCall


class CanonicalizationError(ValueError):
    """El valor no admite una forma canónica única."""


def _check(value: Any) -> None:
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, str):
        try:
            ensure_nfc(value)
        except ValueError as exc:
            raise CanonicalizationError(str(exc)) from exc
        return
    if isinstance(value, list):
        for item in value:
            _check(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError("las claves deben ser strings")
            _check(key)
            _check(item)
        return
    raise CanonicalizationError(f"tipo no canonicalizable: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    _check(value)
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalizationError(f"clave duplicada: {key}")
        result[key] = value
    return result


def _reject_number(token: str) -> None:
    raise CanonicalizationError(f"número no admitido: {token}")


def loads_strict(raw: bytes | str) -> Any:
    """Parsea JSON rechazando claves duplicadas, floats, NaN e infinitos."""
    return json.loads(
        raw,
        object_pairs_hook=_no_duplicate_keys,
        parse_float=_reject_number,
        parse_constant=_reject_number,
    )


class CanonicalRequest(StrictModel):
    """ToolCall validada más el contexto que solo deriva el servidor."""

    call: ToolCall
    principal_id: Identifier
    environment_id: Identifier
    resource_version: int = Field(ge=0)

    def canonical_bytes(self) -> bytes:
        return canonical_json(self.model_dump(mode="json"))

    def digest(self) -> str:
        return sha256_hex(self.canonical_bytes())
