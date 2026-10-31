"""Dobles de desarrollo de los puertos de P2/P3/P4.

No son evidencia de protección real: FakeGateway usa una tabla de decisiones fija,
no el motor de políticas ni el gateway de P3. Sí firma capacidades reales y llama al
ejecutor real, para probar el límite que posee P1.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Request

from wallba.contracts.canonical import CanonicalRequest
from wallba.contracts.capability import Capability, capability_signing_bytes, compute_signature
from wallba.contracts.decision import DecisionEnvelope, RequestView
from wallba.contracts.ports import AuditEventDraft, HarnessObservation, Principal, Role
from wallba.foundation.http import ApiError

CAPABILITY_SECRET = b"s" * 32
KEY_ID = "test-key"
EXECUTOR_TOKEN = "e" * 32
BASELINE_TOKEN = "b" * 32
ENVIRONMENT_ID = "protected-fixture"

ROLE_HEADER = "x-test-role"


class FakeAuthorizer:
    """Sustituye RBAC/CSRF de P3: el rol llega en una cabecera solo de test."""

    def require(self, request: Request, role: Role, *, mutation: bool) -> Principal:
        granted = request.headers.get(ROLE_HEADER)
        if granted is None:
            raise ApiError(401, "UNAUTHENTICATED", "Sin identidad")
        if granted != role:
            raise ApiError(403, "FORBIDDEN", "Sin rol")
        if mutation and request.headers.get("x-csrf-token") != "test-csrf":
            raise ApiError(403, "CSRF_FAILED", "CSRF inválido")
        return Principal(principal_id="demo-operator", kind="human", roles=[role])


class FakeAuditSink:
    def __init__(self) -> None:
        self.events: list[AuditEventDraft] = []
        self.fail = False

    def append(self, event: AuditEventDraft, transaction: object) -> str:
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append(event)
        return str(uuid.uuid4())


def sign_capability(
    request: CanonicalRequest,
    *,
    secret: bytes = CAPABILITY_SECRET,
    key_id: str = KEY_ID,
    execution_id: str | None = None,
    nonce: str | None = None,
    expires_in: int = 30,
    now: datetime | None = None,
    **overrides: object,
) -> Capability:
    now = now or datetime.now(timezone.utc)
    fields = {
        "execution_id": execution_id or str(uuid.uuid4()),
        "request_digest": request.digest(),
        "principal_id": request.principal_id,
        "environment_id": request.environment_id,
        "resource_version": request.resource_version,
        "policy_id": "demo-policy",
        "policy_version": 1,
        "expires_at": (now + timedelta(seconds=expires_in)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": nonce or secrets.token_hex(16),
        "key_id": key_id,
        "signature": "0" * 64,
        **overrides,
    }
    unsigned = Capability(**fields)
    return unsigned.model_copy(
        update={"signature": compute_signature(capability_signing_bytes(unsigned), secret)}
    )


# Tabla fija solo para pruebas: (tool, resource_id, destinatario) -> decisión.
def _fixture_decision(call) -> tuple[str, str, str]:
    if call.tool == "file.read":
        if call.resource_id == "file:public-guide":
            return "ALLOW", "RULE_ALLOW", "LOW"
        return "DENY", "RULE_DENY", "HIGH"
    if call.tool == "db.query":
        return "ALLOW", "RULE_ALLOW", "LOW"
    if call.tool == "record.delete":
        return "DENY", "RULE_DENY", "HIGH"
    if call.parameters.to.endswith("@example.test"):
        return "REQUIRE_APPROVAL", "APPROVAL_REQUIRED", "HIGH"
    return "DENY", "RULE_DENY", "HIGH"


class FakeGateway:
    """Doble de ToolGateway. Nunca debe activarse fuera de pruebas."""

    def __init__(self, executor_client) -> None:
        self._executor = executor_client
        self._views: dict[str, RequestView] = {}
        self._calls: dict[str, object] = {}
        self.submitted: list[object] = []
        self.fail_submit = False

    def _dispatch(self, call, decision: DecisionEnvelope, principal_id: str) -> RequestView:
        version = self._executor.get(
            f"/internal/resources/{call.resource_id}/version",
            headers={"Authorization": f"Bearer {EXECUTOR_TOKEN}"},
        ).json()["version"]
        request = CanonicalRequest(
            call=call, principal_id=principal_id, environment_id=ENVIRONMENT_ID, resource_version=version
        )
        capability = sign_capability(request)
        response = self._executor.post(
            "/internal/execute",
            json={
                "request": request.model_dump(mode="json"),
                "capability": capability.model_dump(mode="json"),
            },
            headers={"Authorization": f"Bearer {EXECUTOR_TOKEN}"},
        )
        response.raise_for_status()
        return RequestView(
            request_id=call.request_id,
            state=response.json()["state"],
            decision=decision,
            approval_id=None,
            execution_id=capability.execution_id,
        )

    def submit(self, call, principal: Principal, idempotency_key: str) -> RequestView:
        if self.fail_submit:
            raise RuntimeError("gateway caído")
        self.submitted.append(call)
        self._calls[call.request_id] = (call, principal.principal_id)
        effect, reason, risk = _fixture_decision(call)
        decision = DecisionEnvelope(
            request_id=call.request_id,
            decision=effect,
            reason_code=reason,
            matched_rule_ids=["fixture-rule"],
            policy_id="demo-policy",
            policy_version=1,
            risk=risk,
        )
        if effect == "DENY":
            view = RequestView(
                request_id=call.request_id, state="DENIED", decision=decision, approval_id=None, execution_id=None
            )
        elif effect == "REQUIRE_APPROVAL":
            view = RequestView(
                request_id=call.request_id,
                state="PENDING_APPROVAL",
                decision=decision,
                approval_id=str(uuid.uuid4()),
                execution_id=None,
            )
        else:
            view = self._dispatch(call, decision, principal.principal_id)
        self._views[call.request_id] = view
        return view

    def get(self, request_id: str, principal: Principal) -> RequestView:
        return self._views[request_id]

    def resolve(self, request_id: str, *, approved: bool) -> None:
        """Simula la decisión de un humano distinto; el runner nunca la invoca."""
        call, principal_id = self._calls[request_id]
        current = self._views[request_id]
        if approved:
            executed = self._dispatch(call, current.decision, principal_id)
            self._views[request_id] = executed.model_copy(update={"approval_id": current.approval_id})
        else:
            self._views[request_id] = current.model_copy(update={"state": "REJECTED"})


class FakeHarness:
    def __init__(self, observation: HarnessObservation | None = None) -> None:
        self.observation = observation

    def observe(self, scenario_id: str, run_id: str, request_ids: list[str]) -> HarnessObservation | None:
        return self.observation
