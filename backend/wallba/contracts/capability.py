"""Capacidad interna firmada: formato compartido entre gateway (P3) y ejecutor (P1)."""

from __future__ import annotations

import hashlib
import hmac
from typing import Literal

from pydantic import Field

from wallba.contracts.canonical import CanonicalRequest, canonical_json
from wallba.contracts.common import Identifier, Sha256Hex, StrictModel, Uuid

CAPABILITY_AUDIENCE = "wallba-executor"
CAPABILITY_TTL_SECONDS = 30
CLOCK_TOLERANCE_SECONDS = 2


class Capability(StrictModel):
    version: Literal[1] = 1
    execution_id: Uuid
    request_digest: Sha256Hex
    principal_id: Identifier
    environment_id: Identifier
    resource_version: int = Field(ge=0)
    policy_id: Identifier
    policy_version: int = Field(ge=1)
    # RFC3339 UTC como string: el JSON canónico no admite otros tipos de fecha.
    expires_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    nonce: str = Field(pattern=r"^[0-9a-f]{32,128}$")
    audience: Literal["wallba-executor"] = CAPABILITY_AUDIENCE
    key_id: Identifier
    signature: Sha256Hex


def capability_signing_bytes(capability: Capability) -> bytes:
    return canonical_json(capability.model_dump(mode="json", exclude={"signature"}))


def compute_signature(signing_bytes: bytes, secret: bytes) -> str:
    return hmac.new(secret, signing_bytes, hashlib.sha256).hexdigest()


class ExecuteCommand(StrictModel):
    """Cuerpo de la llamada interna gateway -> ejecutor protegido."""

    request: CanonicalRequest
    capability: Capability
