"""Persona 3 adapter: evaluate P2 while sharing the claim's DB transaction."""

import hashlib
import json

from sqlalchemy import text

from wallba.contracts.decision import DecisionEnvelope
from wallba.foundation.http import ApiError
from wallba.policy.evaluator import evaluate
from wallba.policy.models import EvaluationRequest, TrustedContext
from wallba.policy.schemas import (
    canonical_bytes,
    snapshot_from_document,
    validate_mapping,
)


class PolicyAdapter:
    def snapshot(self, connection):
        row = (
            connection.execute(
                text(
                    "SELECT v.normalized_json,v.checksum FROM policy_activation a "
                    "JOIN policy_versions v ON v.policy_id=a.policy_id AND v.version=a.version "
                    "WHERE a.singleton_id=1"
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        try:
            payload = row["normalized_json"].encode("utf-8")
            if hashlib.sha256(payload).hexdigest() != row["checksum"]:
                raise ValueError()
            report = validate_mapping(json.loads(payload))
            if (
                not report.valid
                or report.document is None
                or canonical_bytes(report.document) != payload
            ):
                raise ValueError()
            return snapshot_from_document(report.document)
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise ApiError(503, "POLICY_INVALID", "Política activa inválida") from exc

    def decide(self, canonical, principal, snapshot, now):
        request = EvaluationRequest.model_validate(
            canonical.call.model_dump(mode="json")
        )
        context = TrustedContext(
            principal_id=principal.principal_id,
            agent_id=canonical.call.agent_id,
            roles=["agent"] if principal.kind == "agent" else list(principal.roles),
            environment_id=canonical.environment_id,
            server_time=now,
            resource_version=str(canonical.resource_version),
        )
        return DecisionEnvelope.model_validate(
            evaluate(request, context, snapshot).model_dump(mode="json")
        )
