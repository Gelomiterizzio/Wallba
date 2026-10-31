import secrets
from datetime import timedelta

from wallba.contracts.capability import (
    Capability,
    capability_signing_bytes,
    compute_signature,
)


class CapabilityIssuer:
    def __init__(self, secret: bytes, key_id: str):
        if len(secret) < 32:
            raise ValueError("La clave de capacidad debe tener al menos 32 bytes")
        self._secret, self.key_id = secret, key_id

    def issue(self, request, decision, execution_id, now):
        if decision.policy_id is None or decision.policy_version is None:
            raise ValueError("No se firma capacidad sin política")
        unsigned = Capability(
            execution_id=execution_id,
            request_digest=request.digest(),
            principal_id=request.principal_id,
            environment_id=request.environment_id,
            resource_version=request.resource_version,
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            expires_at=(now + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            nonce=secrets.token_hex(32),
            key_id=self.key_id,
            signature="0" * 64,
        )
        return unsigned.model_copy(
            update={
                "signature": compute_signature(
                    capability_signing_bytes(unsigned), self._secret
                )
            }
        )
