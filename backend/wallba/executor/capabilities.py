"""Verificación de la capacidad firmada, sin decidir permisos de política."""

from __future__ import annotations

import hmac
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone

from wallba.contracts.canonical import CanonicalRequest
from wallba.contracts.capability import (
    CAPABILITY_AUDIENCE,
    CAPABILITY_TTL_SECONDS,
    CLOCK_TOLERANCE_SECONDS,
    Capability,
    capability_signing_bytes,
    compute_signature,
)
from wallba.executor.errors import CapabilityRejected

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CapabilityVerifier:
    def __init__(
        self,
        keys: Mapping[str, bytes],
        environment_id: str,
        clock: Clock = utc_now,
    ) -> None:
        self._keys = dict(keys)
        self._environment_id = environment_id
        self._clock = clock

    def verify(self, request: CanonicalRequest, capability: Capability) -> None:
        """Rechaza antes de reclamar nonce o tocar un recurso."""
        self._verify_signature(capability)
        if capability.audience != CAPABILITY_AUDIENCE:
            raise CapabilityRejected("AUDIENCE_MISMATCH")
        if capability.environment_id != self._environment_id:
            raise CapabilityRejected("ENVIRONMENT_MISMATCH")
        if request.environment_id != capability.environment_id:
            raise CapabilityRejected("ENVIRONMENT_MISMATCH")
        if request.principal_id != capability.principal_id:
            raise CapabilityRejected("PRINCIPAL_MISMATCH")
        self._verify_expiry(capability)
        if not hmac.compare_digest(request.digest(), capability.request_digest):
            raise CapabilityRejected("DIGEST_MISMATCH")
        if request.resource_version != capability.resource_version:
            raise CapabilityRejected("STALE_RESOURCE")

    def _verify_signature(self, capability: Capability) -> None:
        secret = self._keys.get(capability.key_id)
        if secret is None:
            raise CapabilityRejected("UNKNOWN_KEY")
        expected = compute_signature(capability_signing_bytes(capability), secret)
        if not hmac.compare_digest(expected, capability.signature):
            raise CapabilityRejected("INVALID_SIGNATURE")

    def _verify_expiry(self, capability: Capability) -> None:
        expires_at = datetime.strptime(capability.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        now = self._clock()
        tolerance = timedelta(seconds=CLOCK_TOLERANCE_SECONDS)
        if now > expires_at + tolerance:
            raise CapabilityRejected("CAPABILITY_EXPIRED")
        # Una capacidad con TTL mayor al contractual tampoco es válida.
        if expires_at > now + timedelta(seconds=CAPABILITY_TTL_SECONDS) + tolerance:
            raise CapabilityRejected("CAPABILITY_TTL_TOO_LONG")
