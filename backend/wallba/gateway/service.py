"""Persona 3: durable enforcement, idempotency, exact claims and recovery.

All authorization decisions and audit intention commit BEFORE contacting the
executor. An uncertain dispatch is never retried, even after process restart.
"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import insert, select, update

from wallba.approvals.models import approvals
from wallba.contracts.canonical import CanonicalRequest, canonical_json, sha256_hex
from wallba.contracts.decision import DecisionEnvelope, ExecutionReceipt
from wallba.contracts.ports import Principal
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER
from wallba.foundation.database import write_transaction
from wallba.foundation.http import ApiError
from wallba.foundation.models import DemoRunRow
from wallba.gateway.executor_client import ExecutorRejected
from wallba.gateway.identity import refresh_identity
from wallba.gateway.normalization import idempotency_key, input_digest
from wallba.gateway.policy_adapter import PolicyAdapter
from wallba.gateway.repository import (
    canonical_from,
    request_row,
    set_state,
    stamp,
    utc,
    view_of,
)
from wallba.gateway.schema import events, executions, requests


class GatewayService:
    def __init__(
        self,
        engine,
        executor,
        issuer,
        clock,
        audit,
        *,
        environment_id="protected-fixture",
        policy=None,
    ):
        self.engine, self.executor, self.issuer = engine, executor, issuer
        self.clock, self.audit, self.environment_id = clock, audit, environment_id
        self.policy = policy or PolicyAdapter()

    def _now(self):
        return utc(self.clock.now())

    def _event(self, connection, event_type, row=None, *, principal_id=None, **payload):
        event = {"event_type": event_type, "occurred_at": stamp(self._now()), **payload}
        if row is not None:
            canonical = row["canonical_json"]
            call = canonical["call"]
            event.update(
                request_id=row["request_id"],
                run_id=row["demo_run_id"],
                request_digest=row["request_digest"],
                # Sin esto la auditoría no se puede filtrar por herramienta, agente o entorno.
                agent_id=call["agent_id"],
                tool=call["tool"],
                resource_id=call["resource_id"],
                environment_id=canonical["environment_id"],
            )
            event["principal_id"] = principal_id or row["principal_id"]
        elif principal_id:
            event["principal_id"] = principal_id
        try:
            return self.audit.append(event, connection)
        except Exception as exc:
            raise ApiError(
                503,
                "AUDIT_UNAVAILABLE",
                "No se pudo registrar la auditoría obligatoria",
            ) from exc

    def _version(self, resource_id):
        try:
            version = self.executor.resource_version(resource_id)
            if type(version) is not int or version < 0:
                raise ValueError()
            return version
        except Exception as exc:
            raise ApiError(
                503, "AUTHORIZATION_UNAVAILABLE", "No se pudo comprobar el recurso"
            ) from exc

    @staticmethod
    def _active_run(connection):
        return connection.execute(
            select(DemoRunRow.run_id).where(
                DemoRunRow.status.in_(
                    ["RUNNING", "WAITING_APPROVAL", "WAITING_ADMIN_INPUT"]
                )
            )
        ).scalar_one_or_none()

    def _snapshot_decision(self, connection, canonical, principal):
        try:
            snapshot = self.policy.snapshot(connection)
            decision = self.policy.decide(canonical, principal, snapshot, self._now())
            return snapshot, decision
        except ApiError as exc:
            reason = (
                exc.code
                if exc.code == "POLICY_INVALID"
                else "AUTHORIZATION_UNAVAILABLE"
            )
        # The policy port can fail with storage, decoding or evaluator errors.
        # All of them deliberately collapse to a fail-closed decision.
        except Exception:  # noqa: BLE001
            reason = "AUTHORIZATION_UNAVAILABLE"
        return None, DecisionEnvelope(
            request_id=canonical.call.request_id,
            decision="DENY",
            reason_code=reason,
            matched_rule_ids=[],
            policy_id=None,
            policy_version=None,
            risk="HIGH",
        )

    def _existing(self, connection, call, principal, key, digest):
        existing = (
            connection.execute(
                select(requests).where(
                    requests.c.principal_id == principal.principal_id,
                    requests.c.idempotency_key == key,
                )
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["input_digest"] != digest:
                raise ApiError(
                    409,
                    "IDEMPOTENCY_CONFLICT",
                    "La clave ya corresponde a otra solicitud",
                )
            canonical_from(existing)
            return view_of(connection, existing)
        if request_row(connection, call.request_id):
            raise ApiError(
                409, "REQUEST_CONFLICT", "Solicitud incompatible con el estado guardado"
            )
        return None

    def submit(
        self,
        call,
        principal: Principal,
        idempotency_key_value: str,
        *,
        credential_hash=None,
    ):
        try:
            call = TOOL_CALL_ADAPTER.validate_python(call.model_dump(mode="python"))
            canonical_json(call.model_dump(mode="json"))
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise ApiError(422, "VALIDATION_ERROR", "Solicitud no válida") from exc
        key = idempotency_key(idempotency_key_value)
        digest = input_digest(call)
        with write_transaction(self.engine) as connection:
            principal = refresh_identity(connection, principal, call, credential_hash)
            found = self._existing(connection, call, principal, key, digest)
            if found:
                return found
        # Network IO NEVER runs under a control-DB transaction.
        version = self._version(call.resource_id)
        claim = None
        with write_transaction(self.engine) as connection:
            principal = refresh_identity(connection, principal, call, credential_hash)
            found = self._existing(connection, call, principal, key, digest)
            if found:
                return found
            canonical = CanonicalRequest(
                call=call,
                principal_id=principal.principal_id,
                environment_id=self.environment_id,
                resource_version=version,
            )
            snapshot, decision = self._snapshot_decision(
                connection, canonical, principal
            )
            state = {
                "DENY": "DENIED",
                "ALLOW": "READY",
                "REQUIRE_APPROVAL": "PENDING_APPROVAL",
            }[decision.decision]
            now = self._now()
            row = {
                "request_id": call.request_id,
                "principal_id": principal.principal_id,
                "principal_kind": principal.kind,
                "credential_hash": credential_hash,
                "agent_id": call.agent_id,
                "idempotency_key": key,
                "input_digest": digest,
                "canonical_json": canonical.model_dump(mode="json"),
                "request_digest": canonical.digest(),
                "state": state,
                "row_version": 1,
                "decision_json": decision.model_dump(mode="json"),
                "policy_checksum": snapshot.checksum if snapshot else None,
                "demo_run_id": self._active_run(connection),
                "created_at": stamp(now),
            }
            connection.execute(insert(requests).values(**row))
            self._event(connection, "request_received", row)
            self._event(
                connection,
                "authorization_decided",
                row,
                **decision.model_dump(exclude={"request_id"}),
            )
            if decision.decision == "REQUIRE_APPROVAL":
                if snapshot is None:
                    raise ApiError(
                        503, "AUTHORIZATION_UNAVAILABLE", "Política no disponible"
                    )
                approval_id = str(uuid4())
                connection.execute(
                    insert(approvals).values(
                        approval_id=approval_id,
                        request_id=call.request_id,
                        status="PENDING",
                        row_version=1,
                        snapshot_json=canonical.model_dump(mode="json"),
                        request_digest=canonical.digest(),
                        policy_id=decision.policy_id,
                        policy_version=decision.policy_version,
                        policy_checksum=snapshot.checksum,
                        created_at=stamp(now),
                        expires_at=stamp(now + timedelta(minutes=5)),
                    )
                )
                self._event(
                    connection,
                    "approval_created",
                    row,
                    approval_id=approval_id,
                    status="PENDING",
                )
            elif decision.decision == "ALLOW":
                claim = self.claim(connection, row, canonical, decision)
            result = view_of(connection, request_row(connection, call.request_id))
        if claim:
            return self.dispatch(call.request_id, *claim)
        return result

    def claim(self, connection, row, canonical, decision):
        execution_id = str(uuid4())
        capability = self.issuer.issue(canonical, decision, execution_id, self._now())
        connection.execute(
            insert(executions).values(
                execution_id=execution_id,
                request_id=row["request_id"],
                state="EXECUTING",
                nonce_hash=sha256_hex(capability.nonce.encode()),
                claimed_at=stamp(self._now()),
            )
        )
        set_state(connection, row["request_id"], "EXECUTING")
        self._event(
            connection,
            "execution_claimed",
            row,
            execution_id=execution_id,
            state="EXECUTING",
        )
        return canonical, capability

    def dispatch(self, request_id, canonical, capability):
        try:
            receipt = self.executor.execute(canonical, capability)
            receipt = ExecutionReceipt.model_validate(receipt)
            if (
                receipt.request_id != request_id
                or receipt.execution_id != capability.execution_id
            ):
                raise ValueError("Receipt ajeno")
            return self._record_result(
                request_id, capability.execution_id, receipt.state, receipt
            )
        except ExecutorRejected as exc:
            return self._record_result(
                request_id, capability.execution_id, "FAILED", None, exc.code
            )
        # After a possible side effect, any client/validation/persistence error
        # is intentionally represented as UNKNOWN; retrying would be unsafe.
        except Exception:  # noqa: BLE001
            # This includes failure to record the result after the tool ran.
            # Durable claim remains; never issue a second execution.
            try:
                return self._record_result(
                    request_id,
                    capability.execution_id,
                    "UNKNOWN",
                    None,
                    "EXECUTION_UNKNOWN",
                )
            except Exception as exc:
                raise ApiError(
                    503,
                    "EXECUTION_UNKNOWN",
                    "Resultado incierto; no repitas la operación",
                ) from exc

    def _record_result(self, request_id, execution_id, state, receipt, reason=None):
        with write_transaction(self.engine) as connection:
            current = (
                connection.execute(
                    select(executions).where(executions.c.execution_id == execution_id)
                )
                .mappings()
                .one()
            )
            if current["state"] in {"SUCCEEDED", "FAILED"}:
                return view_of(connection, request_row(connection, request_id))
            connection.execute(
                update(executions)
                .where(executions.c.execution_id == execution_id)
                .values(
                    state=state,
                    receipt_json=receipt.model_dump(mode="json") if receipt else None,
                    reason_code=reason,
                )
            )
            set_state(connection, request_id, state)
            self._event(
                connection,
                {
                    "SUCCEEDED": "execution_completed",
                    "FAILED": "execution_failed",
                    "UNKNOWN": "execution_unknown",
                }[state],
                request_row(connection, request_id),
                execution_id=execution_id,
                evidence_id=receipt.evidence_id if receipt else None,
                state=state,
                reason_code=reason,
            )
            return view_of(connection, request_row(connection, request_id))

    def get(self, request_id, principal):
        with self.engine.connect() as connection:
            row = request_row(connection, request_id)
            if row is None or (
                principal.kind == "agent"
                and row["principal_id"] != principal.principal_id
            ):
                raise ApiError(404, "NOT_FOUND", "Solicitud no encontrada")
            if (
                principal.kind == "human"
                and "viewer" not in principal.roles
                and row["principal_id"] != principal.principal_id
            ):
                raise ApiError(403, "ROLE_DENIED", "Se requiere rol viewer")
            return view_of(connection, row)

    def reconcile(self, request_id):
        with self.engine.connect() as connection:
            execution = (
                connection.execute(
                    select(executions).where(executions.c.request_id == request_id)
                )
                .mappings()
                .first()
            )
        if not execution or execution["state"] not in {"UNKNOWN", "EXECUTING"}:
            return
        try:
            receipt = self.executor.receipt(execution["execution_id"])
            if receipt is not None:
                receipt = ExecutionReceipt.model_validate(receipt)
                if (
                    receipt.request_id != request_id
                    or receipt.execution_id != execution["execution_id"]
                ):
                    raise ValueError()
        # Receipt transports and receipt parsing failures are both ambiguous.
        except Exception:  # noqa: BLE001
            receipt = None
        self._record_result(
            request_id,
            execution["execution_id"],
            receipt.state if receipt else "UNKNOWN",
            receipt,
            None if receipt else "EXECUTION_UNKNOWN",
        )

    def recover(self):
        with self.engine.connect() as connection:
            pending = (
                connection.execute(
                    select(executions.c.request_id).where(
                        executions.c.state.in_(["EXECUTING", "UNKNOWN"])
                    )
                )
                .scalars()
                .all()
            )
        for request_id in pending:
            self.reconcile(request_id)

    def request_events(self, request_id, principal):
        self.get(request_id, principal)
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    select(events)
                    .where(events.c.request_id == request_id)
                    .order_by(events.c.occurred_at, events.c.event_id)
                ).mappings()
            ]
