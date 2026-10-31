"""Runner paired, con FakeGateway. No es evidencia de la protección real (WAL-P1-008).

El ejecutor y el baseline sí son los reales de P1; la decisión viene de una tabla fija.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from conftest import OPERATOR, VIEWER, Lab

from wallba.contracts.ports import HarnessObservation, Principal

RUNS = "/api/v1/demo-runs"


def start(lab: Lab, scenario_id: str, seed: int = 7) -> str:
    response = lab.client.post(
        RUNS, json={"scenario_id": scenario_id, "seed": seed, "mode": "paired"}, headers=OPERATOR
    )
    assert response.status_code == 202, response.text
    return response.json()["run_id"]


def view(lab: Lab, run_id: str) -> dict[str, Any]:
    response = lab.client.get(f"{RUNS}/{run_id}", headers=VIEWER)
    assert response.status_code == 200, response.text
    return response.json()


def evidence(lab: Lab, run_id: str) -> dict[str, Any]:
    response = lab.client.get(f"{RUNS}/{run_id}/evidence", headers=VIEWER)
    assert response.status_code == 200, response.text
    return response.json()


def test_s04_baseline_deletes_and_protected_keeps_row(lab: Lab) -> None:
    run = view(lab, start(lab, "S04"))
    assert run["status"] == "COMPLETED"

    baseline, protected = run["baseline"], run["protected"]
    assert baseline["state"] == "OBSERVED"
    assert baseline["receipts"][0]["effect_count"] == 1
    assert baseline["before"]["record_count"] - baseline["after"]["record_count"] == 1

    assert protected["state"] == "OBSERVED"
    assert protected["decisions"][0]["decision"] == "DENY"
    assert protected["receipts"] == []
    assert protected["before"]["state_digest"] == protected["after"]["state_digest"]
    # No despacho: el journal del ejecutor protegido no registró ninguna ejecución.
    assert protected["after"]["journal_count"] == 0


def test_both_sides_start_from_same_functional_state(lab: Lab) -> None:
    run = view(lab, start(lab, "S04"))
    assert run["baseline"]["before"]["state_digest"] == run["protected"]["before"]["state_digest"]
    assert run["baseline"]["environment_id"] != run["protected"]["environment_id"]


def test_same_tool_call_reaches_both_sides(lab: Lab) -> None:
    run_id = start(lab, "S04")
    manifest = evidence(lab, run_id)["manifest"]
    assert len(manifest["calls"]) == 1
    assert lab.gateway.submitted[0].request_id == manifest["calls"][0]["call"]["request_id"]


def test_s01_allowed_read_goes_through_real_executor(lab: Lab) -> None:
    run = view(lab, start(lab, "S01"))
    protected = run["protected"]
    assert protected["decisions"][0]["decision"] == "ALLOW"
    assert protected["receipts"][0]["state"] == "SUCCEEDED"
    assert protected["after"]["journal_count"] == 1
    assert run["baseline"]["receipts"][0]["result_digest"] == protected["receipts"][0]["result_digest"]


def test_s02_restricted_read_is_not_dispatched(lab: Lab) -> None:
    protected = view(lab, start(lab, "S02"))["protected"]
    assert protected["decisions"][0]["decision"] == "DENY"
    assert protected["after"]["journal_count"] == 0


def test_s05_external_email_only_reaches_baseline_outbox(lab: Lab) -> None:
    run = view(lab, start(lab, "S05"))
    assert run["baseline"]["after"]["outbox_count"] == 1
    assert run["protected"]["after"]["outbox_count"] == 0


def test_s08_read_allowed_then_delete_denied(lab: Lab) -> None:
    run = view(lab, start(lab, "S08"))
    decisions = [decision["decision"] for decision in run["protected"]["decisions"]]
    assert decisions == ["ALLOW", "DENY"]
    assert run["protected"]["after"]["record_count"] == 8
    assert run["baseline"]["after"]["record_count"] == 7
    assert "determinista" in run["agent_kind_label"]


class TestApprovalFlow:
    def test_s06_waits_without_autoapproval(self, lab: Lab) -> None:
        run = view(lab, start(lab, "S06"))
        assert run["status"] == "WAITING_APPROVAL"
        assert run["protected"]["state"] == "WAITING_APPROVAL"
        assert run["protected"]["receipts"] == []
        # El baseline ya ejecutó; el protegido no tiene correo mientras nadie apruebe.
        assert run["baseline"]["after"]["outbox_count"] == 1
        again = view(lab, run["run_id"])
        assert again["status"] == "WAITING_APPROVAL"

    def test_s06_resumes_after_human_approval(self, lab: Lab) -> None:
        run_id = start(lab, "S06")
        request_id = view(lab, run_id)["protected"]["request_ids"][0]
        lab.gateway.resolve(request_id, approved=True)
        run = view(lab, run_id)
        assert run["status"] == "COMPLETED"
        assert run["protected"]["after"]["outbox_count"] == 1
        assert run["protected"]["receipts"][0]["effect_count"] == 1

    def test_s06_rejection_is_recorded_without_email(self, lab: Lab) -> None:
        run_id = start(lab, "S06")
        request_id = view(lab, run_id)["protected"]["request_ids"][0]
        lab.gateway.resolve(request_id, approved=False)
        run = view(lab, run_id)
        assert run["status"] == "COMPLETED"
        assert run["protected"]["after"]["outbox_count"] == 0
        assert run["protected"]["receipts"] == []

    def test_waiting_run_blocks_a_second_run(self, lab: Lab) -> None:
        start(lab, "S06")
        response = lab.client.post(
            RUNS, json={"scenario_id": "S01", "seed": 1, "mode": "paired"}, headers=OPERATOR
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "DEMO_ALREADY_ACTIVE"

    def test_a_new_run_is_allowed_after_completion(self, lab: Lab) -> None:
        run_id = start(lab, "S06")
        request_id = view(lab, run_id)["protected"]["request_ids"][0]
        lab.gateway.resolve(request_id, approved=True)
        start(lab, "S01")


class TestSpecialSequences:
    @pytest.mark.parametrize("scenario", ["S07", "S09", "S10"])
    def test_without_harness_protected_is_incomplete_never_pass(self, lab: Lab, scenario: str) -> None:
        run = view(lab, start(lab, scenario))
        assert run["status"] == "INCOMPLETE"
        assert run["protected"]["state"] == "INCOMPLETE"
        assert run["protected"]["reason"] == "HARNESS_UNAVAILABLE"

    def test_s09_baseline_is_not_applicable_with_reason(self, lab: Lab) -> None:
        run = view(lab, start(lab, "S09"))
        assert run["baseline"]["state"] == "NOT_APPLICABLE"
        assert run["baseline"]["reason"]
        assert run["baseline"]["receipts"] == []

    def test_s09_waits_for_admin_step_and_correlates_observation(self, lab_with_harness: Lab) -> None:
        lab = lab_with_harness
        run_id = start(lab, "S09")
        assert view(lab, run_id)["status"] == "WAITING_ADMIN_INPUT"
        lab.harness.observation = HarnessObservation(state="OBSERVED", note="422 observado; activa intacta")
        run = view(lab, run_id)
        assert run["status"] == "COMPLETED"
        assert run["protected"]["reason"] == "422 observado; activa intacta"

    def test_s10_baseline_repeats_the_effect(self, lab_with_harness: Lab) -> None:
        run = view(lab_with_harness, start(lab_with_harness, "S10"))
        assert run["baseline"]["after"]["outbox_count"] == 2
        assert run["status"] == "WAITING_APPROVAL"

    def test_s07_baseline_runs_altered_body(self, lab_with_harness: Lab) -> None:
        run = view(lab_with_harness, start(lab_with_harness, "S07"))
        assert run["baseline"]["after"]["outbox_count"] == 1
        assert run["status"] == "WAITING_APPROVAL"

    def test_harness_unknown_is_preserved(self, lab_with_harness: Lab) -> None:
        lab = lab_with_harness
        run_id = start(lab, "S07")
        lab.harness.observation = HarnessObservation(state="UNKNOWN", note="sin evidencia")
        assert view(lab, run_id)["status"] == "UNKNOWN"


class TestFailures:
    def test_gateway_failure_is_unknown_and_keeps_baseline_evidence(self, lab: Lab) -> None:
        lab.gateway.fail_submit = True
        run_id = start(lab, "S04")
        run = view(lab, run_id)
        assert run["status"] == "UNKNOWN"
        assert run["protected"]["state"] == "UNKNOWN"
        assert run["baseline"]["state"] == "OBSERVED"
        assert run["baseline"]["receipts"][0]["effect_count"] == 1
        assert evidence(lab, run_id)["manifest"]["protected"]["state"] == "UNKNOWN"

    def test_baseline_outage_is_recorded(self, lab: Lab, monkeypatch) -> None:
        def down(*args, **kwargs):
            raise httpx.ConnectError("sin red")

        real_request = lab.baseline_client.request

        def flaky(method, url, **kwargs):
            if url.endswith("/internal/baseline/execute"):
                return down()
            return real_request(method, url, **kwargs)

        monkeypatch.setattr(lab.baseline_client, "request", flaky)
        run = view(lab, start(lab, "S04"))
        assert run["status"] == "UNKNOWN"
        assert run["baseline"]["state"] == "UNKNOWN"
        assert run["baseline"]["reason"] == "EXECUTOR_NO_RESPONSE"
        # Sin reintento: el recurso del baseline no se tocó y no se fabricó un receipt.
        assert run["baseline"]["receipts"] == []

    def test_environment_outage_is_incomplete(self, lab: Lab, monkeypatch) -> None:
        def down(*args, **kwargs):
            raise httpx.ConnectError("sin red")

        monkeypatch.setattr(lab.executor_client, "request", down)
        run = view(lab, start(lab, "S04"))
        assert run["status"] == "INCOMPLETE"
        assert run["protected"]["reason"] == "ENVIRONMENT_UNAVAILABLE"

    def test_interrupted_run_is_marked_after_restart(self, lab: Lab) -> None:
        runner = lab.client.app.state.runner_factory(lab.integrations)
        accepted = runner.start("S04", 1, Principal(principal_id="demo-operator", kind="human", roles=["operator"]))
        assert runner.recover_interrupted() == [accepted.run_id]
        run = runner.view(accepted.run_id)
        assert run.status == "INCOMPLETE"
        assert run.protected.reason == "INTERRUPTED"


class TestAuthorization:
    def test_start_requires_operator_and_csrf(self, lab: Lab) -> None:
        body = {"scenario_id": "S04", "seed": 1, "mode": "paired"}
        assert lab.client.post(RUNS, json=body).status_code == 401
        assert lab.client.post(RUNS, json=body, headers=VIEWER).status_code == 403
        assert lab.client.post(RUNS, json=body, headers={"x-test-role": "operator"}).status_code == 403

    @pytest.mark.parametrize(
        "body",
        [
            {"scenario_id": "S04", "seed": 1, "mode": "single"},
            {"scenario_id": "S04", "seed": 1},
            {"scenario_id": "S04", "seed": "1", "mode": "paired"},
            {"scenario_id": "S04", "seed": 1, "mode": "paired", "firewall": False},
            {"scenario_id": "S04", "seed": 1, "mode": "paired", "sql": "DROP TABLE x"},
        ],
    )
    def test_invalid_bodies_are_rejected(self, lab: Lab, body: dict[str, Any]) -> None:
        assert lab.client.post(RUNS, json=body, headers=OPERATOR).status_code == 422

    def test_unknown_run_is_404(self, lab: Lab) -> None:
        missing = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        assert lab.client.get(f"{RUNS}/{missing}", headers=VIEWER).status_code == 404
        assert lab.client.get(f"{RUNS}/{missing}/evidence", headers=VIEWER).status_code == 404

    def test_demo_disabled_profile_blocks_runs(self, lab: Lab) -> None:
        settings = lab.client.app.state.settings
        lab.client.app.state.settings = type(settings)(**{**settings.__dict__, "demo_enabled": False})
        response = lab.client.post(
            RUNS, json={"scenario_id": "S04", "seed": 1, "mode": "paired"}, headers=OPERATOR
        )
        assert response.status_code == 403

    def test_audit_failure_blocks_start(self, lab: Lab) -> None:
        lab.audit.fail = True
        response = lab.client.post(
            RUNS, json={"scenario_id": "S04", "seed": 1, "mode": "paired"}, headers=OPERATOR
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
        assert lab.gateway.submitted == []
        # Sin intención auditada tampoco queda un run ocupando el slot.
        lab.audit.fail = False
        start(lab, "S01")


def test_audit_failure_after_effect_is_unknown_and_keeps_evidence(lab: Lab) -> None:
    runner = lab.client.app.state.runner_factory(lab.integrations)
    principal = Principal(principal_id="demo-operator", kind="human", roles=["operator"])
    accepted = runner.start("S04", 1, principal)
    lab.audit.fail = True
    runner.execute(accepted.run_id, principal)
    lab.audit.fail = False
    assert runner.view(accepted.run_id).status == "UNKNOWN"
    manifest = runner.evidence(accepted.run_id).manifest
    assert manifest["notes"] == ["AUDIT_UNAVAILABLE"]
    assert manifest["observed_assertions"]["baseline"]["records_removed"] == 1


def test_unexpected_runner_error_releases_the_slot(lab: Lab, monkeypatch) -> None:
    runner = lab.client.app.state.runner_factory(lab.integrations)
    principal = Principal(principal_id="demo-operator", kind="human", roles=["operator"])
    accepted = runner.start("S04", 1, principal)

    def boom(*args, **kwargs):
        raise ValueError("error inesperado")

    monkeypatch.setattr(runner, "_run_baseline", boom)
    runner.execute(accepted.run_id, principal)
    run = runner.view(accepted.run_id)
    assert run.status == "INCOMPLETE"
    assert run.protected.reason == "RUNNER_ERROR"
    monkeypatch.undo()
    start(lab, "S01")
