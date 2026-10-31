"""Runner paired: misma intención con y sin firewall, sobre recursos separados.

No existe bypass del lado protegido: solo llega a las herramientas por el
gateway. El runner nunca autoaprueba, y un lado sin observar queda INCOMPLETE o
UNKNOWN en lugar de completarse con la expectativa.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from wallba.agent.scripted import AGENT_KIND_LABEL, ScriptedAgent
from wallba.contracts.api import DemoRunAccepted, DemoRunView, EvidenceView, MatrixRow, SideView
from wallba.contracts.canonical import canonical_json, sha256_hex
from wallba.contracts.decision import RequestView
from wallba.contracts.ports import AuditEventDraft, AuditSink, Principal, ScenarioHarness, ToolGateway
from wallba.contracts.tool_call import EmailSendCall, ToolCall
from wallba.demo.environments import ExecutorUnavailable, HttpEnvironment
from wallba.demo.evidence import build_manifest, side_effect_count
from wallba.demo.scenarios import ALTERED_BODY, BASELINE_NA_S09, SCENARIOS_BY_ID, Scenario
from wallba.foundation.clock import as_utc, utc_now
from wallba.foundation.database import write_transaction
from wallba.foundation.models import ACTIVE_DEMO_STATUSES, DemoRunRow, EvidenceRow

WAITING_DEADLINE = timedelta(minutes=15)
PENDING_REQUEST_STATES = {"RECEIVED", "PENDING_APPROVAL", "READY", "EXECUTING"}


class DemoConflict(Exception):
    """Ya existe un run activo."""


class AuditUnavailable(Exception):
    """No se pudo registrar la intención: el run no empieza."""


def _new_side(environment_id: str) -> SideView:
    return SideView(
        environment_id=environment_id,
        state="PENDING",
        reason=None,
        before=None,
        after=None,
        decisions=[],
        receipts=[],
        request_ids=[],
        approval_ids=[],
    )


def _load_side(data: dict[str, Any]) -> SideView:
    # JSON estricto: los timestamps persistidos vuelven a validarse como UTC.
    return SideView.model_validate_json(json.dumps(data))


class PairedRunner:
    def __init__(
        self,
        engine: Engine,
        gateway: ToolGateway,
        audit: AuditSink,
        baseline: HttpEnvironment,
        protected: HttpEnvironment,
        harness: ScenarioHarness | None = None,
        clock: Callable[[], datetime] = utc_now,
        baseline_env: str = "baseline-fixture",
        protected_env: str = "protected-fixture",
    ) -> None:
        self._engine = engine
        self._gateway = gateway
        self._audit = audit
        self._baseline = baseline
        self._protected = protected
        self._harness = harness
        self._clock = clock
        self._baseline_env = baseline_env
        self._protected_env = protected_env

    # --- Ciclo de vida ------------------------------------------------------------

    def start(self, scenario_id: str, seed: int, principal: Principal) -> DemoRunAccepted:
        """Reclama el único slot activo; el conflicto lo garantiza un índice UNIQUE."""
        self.refresh_active(principal)
        run_id = str(uuid.uuid4())
        state = {
            "baseline": _new_side(self._baseline_env).model_dump(mode="json"),
            "protected": _new_side(self._protected_env).model_dump(mode="json"),
            "transcript_digest": None,
            "audit_event_ids": [],
            "notes": [],
        }
        try:
            with write_transaction(self._engine) as connection:
                with Session(bind=connection) as session:
                    session.add(
                        DemoRunRow(
                            run_id=run_id,
                            scenario_id=scenario_id,
                            seed=seed,
                            fixture_digest=None,
                            status="RUNNING",
                            baseline_env=self._baseline_env,
                            protected_env=self._protected_env,
                            created_by=principal.principal_id,
                            started_at=self._clock(),
                            completed_at=None,
                            state_json=state,
                        )
                    )
                    session.flush()
                    try:
                        event_id = self._audit.append(
                            AuditEventDraft(
                                event_type="demo_started", run_id=run_id, principal_id=principal.principal_id
                            ),
                            connection,
                        )
                    except Exception as exc:  # noqa: BLE001 - sin intención auditada no se ejecuta
                        raise AuditUnavailable(run_id) from exc
                    row = session.get(DemoRunRow, run_id)
                    row.state_json = {**state, "audit_event_ids": [event_id]}
                    session.flush()
        except IntegrityError as exc:
            raise DemoConflict(run_id) from exc
        return DemoRunAccepted(run_id=run_id, status="RUNNING")

    def execute(self, run_id: str, principal: Principal) -> None:
        """Parte en segundo plano de un run. Un error inesperado no deja el slot ocupado."""
        try:
            self._execute(run_id, principal)
        except Exception:  # noqa: BLE001 - el motivo queda registrado en el run
            self._abort(run_id, "RUNNER_ERROR")

    def _abort(self, run_id: str, reason: str) -> None:
        row = self._load_row(run_id)
        scenario = SCENARIOS_BY_ID[row["scenario_id"]]
        calls = ScriptedAgent(run_id, row["seed"]).plan(scenario.id)
        baseline = self._mark_unfinished(_load_side(row["state"]["baseline"]), reason)
        protected = self._mark_unfinished(_load_side(row["state"]["protected"]), reason)
        self._finalize(run_id, scenario, baseline, protected, calls, row["state"]["transcript_digest"], [])

    def _execute(self, run_id: str, principal: Principal) -> None:
        row = self._load_row(run_id)
        scenario = SCENARIOS_BY_ID[row["scenario_id"]]
        agent = ScriptedAgent(run_id, row["seed"])
        calls = agent.plan(scenario.id)
        baseline = _load_side(row["state"]["baseline"])
        protected = _load_side(row["state"]["protected"])
        notes: list[str] = []
        transcript_digest = sha256_hex(
            canonical_json([entry.model_dump(mode="json") for entry in agent.transcript])
        )

        fixture_digest: str | None = None
        try:
            base_env = self._baseline.prepare(run_id, row["seed"])
            prot_env = self._protected.prepare(run_id, row["seed"])
        except (ExecutorUnavailable, httpx.HTTPError):
            baseline = baseline.model_copy(update={"state": "INCOMPLETE", "reason": "ENVIRONMENT_UNAVAILABLE"})
            protected = protected.model_copy(update={"state": "INCOMPLETE", "reason": "ENVIRONMENT_UNAVAILABLE"})
            self._finalize(run_id, scenario, baseline, protected, calls, transcript_digest, notes)
            return

        baseline = baseline.model_copy(update={"before": base_env.snapshot})
        protected = protected.model_copy(update={"before": prot_env.snapshot})
        if (
            base_env.fixture_digest != prot_env.fixture_digest
            or base_env.snapshot.state_digest != prot_env.snapshot.state_digest
        ):
            reason = "FIXTURE_MISMATCH"
            baseline = baseline.model_copy(update={"state": "INCOMPLETE", "reason": reason})
            protected = protected.model_copy(update={"state": "INCOMPLETE", "reason": reason})
            self._finalize(run_id, scenario, baseline, protected, calls, transcript_digest, notes)
            return
        fixture_digest = base_env.fixture_digest

        baseline = self._run_baseline(run_id, scenario, calls, baseline)
        protected = self._run_protected(scenario, calls, protected, principal)
        self._persist_progress(run_id, baseline, protected, fixture_digest, transcript_digest)

        if protected.state in {"WAITING_APPROVAL", "WAITING_ADMIN_INPUT"}:
            self._set_status(run_id, protected.state)
            return
        protected = self._observe_after(run_id, protected)
        self._finalize(run_id, scenario, baseline, protected, calls, transcript_digest, notes)

    def recover_interrupted(self) -> list[str]:
        """Tras un reinicio, un run RUNNING pierde su hilo: se marca, no se repite."""
        with Session(self._engine) as session:
            running = session.scalars(select(DemoRunRow.run_id).where(DemoRunRow.status == "RUNNING")).all()
        for run_id in running:
            self._abort(run_id, "INTERRUPTED")
        return list(running)

    def refresh_active(self, principal: Principal) -> None:
        with Session(self._engine) as session:
            active = session.scalars(
                select(DemoRunRow.run_id).where(DemoRunRow.status.in_(("WAITING_APPROVAL", "WAITING_ADMIN_INPUT")))
            ).all()
        for run_id in active:
            self.refresh(run_id, principal)

    def refresh(self, run_id: str, principal: Principal) -> None:
        """Reanuda un run en espera sin reiniciarlo ni repetir efectos."""
        row = self._load_row(run_id)
        if row["status"] not in {"WAITING_APPROVAL", "WAITING_ADMIN_INPUT"}:
            return
        scenario = SCENARIOS_BY_ID[row["scenario_id"]]
        calls = ScriptedAgent(run_id, row["seed"]).plan(scenario.id)
        baseline = _load_side(row["state"]["baseline"])
        protected = _load_side(row["state"]["protected"])

        if scenario.protected_plan == "gateway":
            protected, finished = self._poll_gateway(protected, principal)
        else:
            protected, finished = self._poll_harness(scenario, run_id, protected)

        if not finished and self._clock() - row["started_at"] > WAITING_DEADLINE:
            protected = protected.model_copy(update={"state": "INCOMPLETE", "reason": "WAIT_DEADLINE_EXCEEDED"})
            finished = True
        if not finished:
            return
        protected = self._observe_after(run_id, protected)
        self._finalize(run_id, scenario, baseline, protected, calls, row["state"]["transcript_digest"], [])

    # --- Lados del run -------------------------------------------------------------

    def _run_baseline(self, run_id: str, scenario: Scenario, calls: list[ToolCall], side: SideView) -> SideView:
        if scenario.baseline_plan == "not_applicable":
            return side.model_copy(update={"state": "NOT_APPLICABLE", "reason": BASELINE_NA_S09})
        receipts = list(side.receipts)
        try:
            for call in self._baseline_sequence(scenario, calls):
                receipts.append(self._baseline.execute_unsafe(call))
        except ExecutorUnavailable:
            # Sin respuesta: el efecto es incierto y no se reintenta.
            side = side.model_copy(update={"state": "UNKNOWN", "reason": "EXECUTOR_NO_RESPONSE", "receipts": receipts})
            return self._observe_baseline(run_id, side)
        except httpx.HTTPStatusError:
            side = side.model_copy(update={"state": "INCOMPLETE", "reason": "BASELINE_ERROR", "receipts": receipts})
            return self._observe_baseline(run_id, side)
        side = side.model_copy(
            update={"state": "OBSERVED", "receipts": receipts, "request_ids": [c.request_id for c in calls]}
        )
        return self._observe_baseline(run_id, side)

    @staticmethod
    def _baseline_sequence(scenario: Scenario, calls: list[ToolCall]) -> list[ToolCall]:
        if scenario.baseline_plan == "repeat_twice":
            return [*calls, *calls]
        if scenario.baseline_plan == "altered_body":
            return [_with_altered_body(call) for call in calls]
        return calls

    def _observe_baseline(self, run_id: str, side: SideView) -> SideView:
        try:
            return side.model_copy(update={"after": self._baseline.snapshot(run_id)})
        except (ExecutorUnavailable, httpx.HTTPError):
            return side

    def _run_protected(
        self, scenario: Scenario, calls: list[ToolCall], side: SideView, principal: Principal
    ) -> SideView:
        needs_harness = scenario.protected_plan != "gateway"
        if needs_harness and self._harness is None:
            # Sin el harness de P2/P3 no hay forma de observar el lado protegido.
            return side.model_copy(update={"state": "INCOMPLETE", "reason": "HARNESS_UNAVAILABLE"})
        if scenario.protected_plan == "control_plane":
            return side.model_copy(update={"state": "WAITING_ADMIN_INPUT"})

        for call in calls:
            key = str(uuid.uuid5(uuid.UUID(call.request_id), "idempotency"))
            try:
                view = self._gateway.submit(call, principal, key)
            except Exception:  # noqa: BLE001 - sin vista del gateway, el resultado es incierto
                return side.model_copy(update={"state": "UNKNOWN", "reason": "GATEWAY_ERROR"})
            side = self._apply_view(side, view)
            if view.state in PENDING_REQUEST_STATES:
                return side.model_copy(update={"state": "WAITING_APPROVAL"})
            if view.state == "UNKNOWN":
                return side.model_copy(update={"state": "UNKNOWN", "reason": "EXECUTION_UNKNOWN"})
        return side.model_copy(update={"state": "OBSERVED"})

    def _apply_view(self, side: SideView, view: RequestView) -> SideView:
        decisions = [d for d in side.decisions if d.request_id != view.request_id]
        if view.decision is not None:
            decisions.append(view.decision)
        receipts = [r for r in side.receipts if r.request_id != view.request_id]
        receipt = view.receipt
        if receipt is None and view.execution_id is not None:
            try:
                receipt = self._protected.receipt(view.execution_id)
            except (ExecutorUnavailable, httpx.HTTPError):
                receipt = None
        if receipt is not None:
            receipts.append(receipt)
        request_ids = side.request_ids if view.request_id in side.request_ids else [*side.request_ids, view.request_id]
        approvals = side.approval_ids
        if view.approval_id is not None and view.approval_id not in approvals:
            approvals = [*approvals, view.approval_id]
        return side.model_copy(
            update={
                "decisions": decisions,
                "receipts": receipts,
                "request_ids": request_ids,
                "approval_ids": approvals,
            }
        )

    def _poll_gateway(self, side: SideView, principal: Principal) -> tuple[SideView, bool]:
        finished = True
        for request_id in side.request_ids:
            try:
                view = self._gateway.get(request_id, principal)
            except Exception:  # noqa: BLE001 - se reintenta en la siguiente consulta
                return side, False
            side = self._apply_view(side, view)
            if view.state in PENDING_REQUEST_STATES:
                finished = False
            elif view.state == "UNKNOWN":
                return side.model_copy(update={"state": "UNKNOWN", "reason": "EXECUTION_UNKNOWN"}), True
        if finished:
            side = side.model_copy(update={"state": "OBSERVED"})
        return side, finished

    def _poll_harness(self, scenario: Scenario, run_id: str, side: SideView) -> tuple[SideView, bool]:
        if self._harness is None:
            return side.model_copy(update={"state": "INCOMPLETE", "reason": "HARNESS_UNAVAILABLE"}), True
        observation = self._harness.observe(scenario.id, run_id, side.request_ids)
        if observation is None:
            return side, False
        side = side.model_copy(
            update={
                "state": observation.state,
                "reason": observation.note,
                "decisions": [*side.decisions, *observation.decisions],
                "receipts": [*side.receipts, *observation.receipts],
            }
        )
        return side, True

    def _observe_after(self, run_id: str, side: SideView) -> SideView:
        try:
            return side.model_copy(update={"after": self._protected.snapshot(run_id)})
        except (ExecutorUnavailable, httpx.HTTPError):
            return side

    @staticmethod
    def _mark_unfinished(side: SideView, reason: str) -> SideView:
        if side.state in {"OBSERVED", "NOT_APPLICABLE", "UNKNOWN"}:
            return side
        return side.model_copy(update={"state": "INCOMPLETE", "reason": reason})

    # --- Persistencia ---------------------------------------------------------------

    def _load_row(self, run_id: str) -> dict[str, Any]:
        with Session(self._engine) as session:
            row = session.get(DemoRunRow, run_id)
            if row is None:
                raise KeyError(run_id)
            return {
                "scenario_id": row.scenario_id,
                "seed": row.seed,
                "status": row.status,
                "state": row.state_json,
                "fixture_digest": row.fixture_digest,
                "started_at": as_utc(row.started_at),
            }

    def _persist_progress(
        self,
        run_id: str,
        baseline: SideView,
        protected: SideView,
        fixture_digest: str | None,
        transcript_digest: str | None,
    ) -> None:
        with write_transaction(self._engine) as connection:
            with Session(bind=connection) as session:
                row = session.get(DemoRunRow, run_id)
                row.fixture_digest = fixture_digest
                row.state_json = {
                    **row.state_json,
                    "baseline": baseline.model_dump(mode="json"),
                    "protected": protected.model_dump(mode="json"),
                    "transcript_digest": transcript_digest,
                }
                session.flush()

    def _set_status(self, run_id: str, status: str) -> None:
        with write_transaction(self._engine) as connection:
            with Session(bind=connection) as session:
                session.get(DemoRunRow, run_id).status = status
                session.flush()

    def _finalize(
        self,
        run_id: str,
        scenario: Scenario,
        baseline: SideView,
        protected: SideView,
        calls: list[ToolCall],
        transcript_digest: str | None,
        notes: list[str],
    ) -> None:
        completed_at = self._clock()
        status = _overall_status(baseline, protected)
        with write_transaction(self._engine) as connection:
            with Session(bind=connection) as session:
                row = session.get(DemoRunRow, run_id)
                # Compare-and-set: dos refrescos simultáneos no producen dos manifests.
                if row.status not in ACTIVE_DEMO_STATUSES:
                    return
                audit_ids = list(row.state_json.get("audit_event_ids", []))
                evidence_id = str(uuid.uuid4())
                completion = AuditEventDraft(
                    event_type="demo_completed",
                    run_id=run_id,
                    principal_id=row.created_by,
                    evidence_id=evidence_id,
                )
                try:
                    audit_ids.append(self._audit.append(completion, connection))
                except Exception:  # noqa: BLE001 - se conserva lo observado y queda sin confirmar
                    # El efecto ya ocurrió: sin traza del resultado el run no se da por completado.
                    status = "UNKNOWN"
                    notes = [*notes, "AUDIT_UNAVAILABLE"]
                manifest, digest = build_manifest(
                    evidence_id=evidence_id,
                    run_id=run_id,
                    scenario=scenario,
                    seed=row.seed,
                    fixture_digest=row.fixture_digest,
                    calls=calls,
                    transcript_digest=transcript_digest,
                    baseline=baseline,
                    protected=protected,
                    audit_event_ids=audit_ids,
                    notes=notes,
                    started_at=as_utc(row.started_at),
                    completed_at=completed_at,
                )
                session.add(
                    EvidenceRow(
                        evidence_id=evidence_id,
                        run_id=run_id,
                        manifest_json=manifest,
                        manifest_digest=digest,
                        schema_version=manifest["schema_version"],
                    )
                )
                row.status = status
                row.completed_at = completed_at
                row.state_json = {
                    **row.state_json,
                    "baseline": baseline.model_dump(mode="json"),
                    "protected": protected.model_dump(mode="json"),
                    "transcript_digest": transcript_digest,
                    "audit_event_ids": audit_ids,
                    "evidence_id": evidence_id,
                }
                session.flush()

    # --- Lectura --------------------------------------------------------------------

    def view(self, run_id: str) -> DemoRunView | None:
        with Session(self._engine) as session:
            row = session.get(DemoRunRow, run_id)
            return _row_to_view(row) if row is not None else None

    def evidence(self, run_id: str) -> EvidenceView | None:
        with Session(self._engine) as session:
            row = session.scalars(select(EvidenceRow).where(EvidenceRow.run_id == run_id)).first()
            if row is None:
                return None
            return EvidenceView(
                evidence_id=row.evidence_id,
                run_id=row.run_id,
                schema_version=row.schema_version,
                manifest=row.manifest_json,
                manifest_digest=row.manifest_digest,
            )

    def matrix(self, scenario_id: str | None = None) -> list[MatrixRow]:
        """Lee evidencia persistida: sin runs terminados, la matriz está vacía."""
        query = (
            select(DemoRunRow, EvidenceRow)
            .join(EvidenceRow, EvidenceRow.run_id == DemoRunRow.run_id)
            .order_by(DemoRunRow.completed_at.desc(), DemoRunRow.run_id.desc())
        )
        if scenario_id is not None:
            query = query.where(DemoRunRow.scenario_id == scenario_id)
        with Session(self._engine) as session:
            return [_matrix_row(run, evidence) for run, evidence in session.execute(query).all()]


def _with_altered_body(call: ToolCall) -> ToolCall:
    if not isinstance(call, EmailSendCall):
        return call
    parameters = call.parameters.model_copy(update={"body": ALTERED_BODY})
    return call.model_copy(update={"parameters": parameters})


def _overall_status(baseline: SideView, protected: SideView) -> str:
    states = {baseline.state, protected.state}
    if "UNKNOWN" in states:
        return "UNKNOWN"
    if states <= {"OBSERVED", "NOT_APPLICABLE"}:
        return "COMPLETED"
    return "INCOMPLETE"


def _row_to_view(row: DemoRunRow) -> DemoRunView:
    state = row.state_json
    return DemoRunView(
        run_id=row.run_id,
        scenario_id=row.scenario_id,
        seed=row.seed,
        status=row.status,
        fixture_digest=row.fixture_digest,
        baseline=_load_side(state["baseline"]),
        protected=_load_side(state["protected"]),
        evidence_id=state.get("evidence_id"),
        started_at=as_utc(row.started_at),
        completed_at=as_utc(row.completed_at) if row.completed_at else None,
        agent_kind_label=AGENT_KIND_LABEL,
    )


def _matrix_row(run: DemoRunRow, evidence: EvidenceRow) -> MatrixRow:
    baseline = _load_side(run.state_json["baseline"])
    protected = _load_side(run.state_json["protected"])
    decision = protected.decisions[-1] if protected.decisions else None
    return MatrixRow(
        scenario_id=run.scenario_id,
        run_id=run.run_id,
        status=run.status,
        risk=decision.risk if decision else None,
        policy_id=decision.policy_id if decision else None,
        policy_version=decision.policy_version if decision else None,
        baseline_state=baseline.state,
        baseline_effect_count=side_effect_count(baseline),
        protected_state=protected.state,
        protected_decision=decision.decision if decision else None,
        protected_reason_code=decision.reason_code if decision else None,
        protected_effect_count=side_effect_count(protected),
        evidence_id=evidence.evidence_id,
        observed_at=as_utc(run.completed_at or run.started_at),
    )
