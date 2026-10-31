"""Persona 3 actual adversarial probes after a human resolves the demo request."""

from sqlalchemy import select

from wallba.approvals.models import approvals
from wallba.contracts.ports import HarnessObservation, Principal
from wallba.foundation.database import write_transaction
from wallba.foundation.http import ApiError
from wallba.gateway.repository import canonical_from, request_row, view_of
from wallba.gateway.schema import events


class Person3Harness:
    def __init__(self, gateway, approval_service):
        self.gateway, self.approvals = gateway, approval_service

    def observe(self, scenario_id, run_id, request_ids):
        if scenario_id not in {"S07", "S10"} or not request_ids:
            return None  # S09 is P2's control-plane scenario, not fabricated here.
        with self.gateway.engine.connect() as connection:
            row = request_row(connection, request_ids[0])
            if row is None or row["demo_run_id"] != run_id:
                return None
            ap = (
                connection.execute(
                    select(approvals).where(approvals.c.request_id == row["request_id"])
                )
                .mappings()
                .one()
            )
            view = view_of(connection, row)
            if ap["status"] != "CONSUMED" or view.receipt is None:
                return None
            canonical = canonical_from(row)
            observed = (
                connection.execute(
                    select(events.c.event_id).where(
                        events.c.run_id == run_id,
                        events.c.event_type == f"person3_{scenario_id.lower()}_blocked",
                    )
                )
                .scalars()
                .all()
            )
        if observed:
            return HarnessObservation(
                state="OBSERVED",
                note="Bloqueo adversarial verificado por Persona 3",
                audit_event_ids=observed,
            )
        try:
            if scenario_id == "S07":
                from wallba.contracts.tool_call import TOOL_CALL_ADAPTER

                payload = canonical.call.model_dump(mode="json")
                payload["parameters"]["body"] = (
                    "Contenido sintético alterado después de aprobar."
                )
                altered = TOOL_CALL_ADAPTER.validate_python(payload)
                self.gateway.submit(
                    altered,
                    Principal(
                        principal_id=row["principal_id"],
                        kind=row["principal_kind"],
                        roles=[],
                    ),
                    row["idempotency_key"],
                    credential_hash=row["credential_hash"],
                )
            else:
                self.approvals.resolve(
                    ap["approval_id"],
                    Principal(principal_id=ap["approver_id"], kind="human", roles=[]),
                    "approve",
                    1,
                    "Prueba de reutilización S10",
                )
        except ApiError as exc:
            expected = (
                "IDEMPOTENCY_CONFLICT"
                if scenario_id == "S07"
                else "APPROVAL_ALREADY_CONSUMED"
            )
            if exc.status_code != 409 or exc.code != expected:
                return HarnessObservation(
                    state="INCOMPLETE",
                    note="El rechazo observado no coincide con la prueba prevista",
                )
            with write_transaction(self.gateway.engine) as connection:
                event_id = self.gateway._event(
                    connection,
                    f"person3_{scenario_id.lower()}_blocked",
                    row,
                    reason_code=exc.code,
                    approval_id=ap["approval_id"],
                )
            return HarnessObservation(
                state="OBSERVED",
                note=f"409 {exc.code}; no se emitió otro claim",
                audit_event_ids=[event_id],
            )
        return HarnessObservation(
            state="UNKNOWN", note="La prueba no produjo el rechazo previsto"
        )
