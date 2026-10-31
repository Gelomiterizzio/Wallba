"""S01 a S10 con el sistema real conectado: sesión, motor, gateway, ejecutor y auditoría.

Sin dobles: es la evidencia de punta a punta que los dobles de P1 y P4 no podían dar.
Corre en proceso, sin red ni contenedores; el aislamiento se prueba en tests/infra.
"""

from __future__ import annotations

from sqlalchemy import text

from wallba.demo.seed import DEMO_USERS, seed_policy, seed_users
from wallba.foundation.database import write_transaction
from wallba.observability.writer import verify_chain

RUNS = "/api/v1/demo-runs"
APPROVAL_SCENARIOS = {"S06", "S07", "S10"}


def start(lab, scenario: str, seed: int = 0) -> str:
    response = lab.client.post(
        RUNS, json={"scenario_id": scenario, "seed": seed, "mode": "paired"}, headers=lab.login("operator")
    )
    assert response.status_code == 202, response.text
    return response.json()["run_id"]


def view(lab, run_id: str) -> dict:
    response = lab.client.get(f"{RUNS}/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def approve_pending(lab) -> None:
    pending = lab.client.get("/api/v1/approvals", params={"status": "PENDING"}).json()["items"]
    assert len(pending) == 1, pending
    response = lab.client.post(
        f"/api/v1/approvals/{pending[0]['approval_id']}/approve",
        json={"expected_version": pending[0]["row_version"], "reason": "Revisión humana de la demostración"},
        headers=lab.login("approver"),
    )
    assert response.status_code == 200, response.text


def run_scenario(lab, scenario: str) -> dict:
    run_id = start(lab, scenario)
    if scenario in APPROVAL_SCENARIOS:
        assert view(lab, run_id)["status"] == "WAITING_APPROVAL"
        approve_pending(lab)
    return view(lab, run_id)


def records(side: dict) -> int:
    return side["after"]["record_count"]


def outbox(side: dict) -> int:
    return side["after"]["outbox_count"]


def journal(side: dict) -> int:
    return side["after"]["journal_count"]


def decisions(side: dict) -> list[str]:
    return [item["decision"] for item in side["decisions"]]


def test_s01_public_read_same_result_on_both_sides(p3_lab) -> None:
    run = run_scenario(p3_lab, "S01")
    assert run["status"] == "COMPLETED"
    protected = run["protected"]
    assert decisions(protected) == ["ALLOW"]
    assert protected["receipts"][0]["state"] == "SUCCEEDED"
    assert run["baseline"]["receipts"][0]["result_digest"] == protected["receipts"][0]["result_digest"]


def test_s02_restricted_read_never_reaches_executor(p3_lab) -> None:
    run = run_scenario(p3_lab, "S02")
    assert decisions(run["protected"]) == ["DENY"]
    assert journal(run["protected"]) == 0
    assert journal(run["baseline"]) == 1


def test_s03_allowed_query(p3_lab) -> None:
    run = run_scenario(p3_lab, "S03")
    assert decisions(run["protected"]) == ["ALLOW"]
    assert run["protected"]["receipts"][0]["effect_count"] == 0


def test_s04_delete_only_succeeds_without_firewall(p3_lab) -> None:
    run = run_scenario(p3_lab, "S04")
    assert records(run["baseline"]) == 7
    assert decisions(run["protected"]) == ["DENY"]
    assert records(run["protected"]) == 8
    assert journal(run["protected"]) == 0


def test_s05_external_email_is_denied(p3_lab) -> None:
    run = run_scenario(p3_lab, "S05")
    assert outbox(run["baseline"]) == 1
    assert decisions(run["protected"]) == ["DENY"]
    assert outbox(run["protected"]) == 0


def test_s06_needs_a_human_and_then_sends_once(p3_lab) -> None:
    run_id = start(p3_lab, "S06")
    waiting = view(p3_lab, run_id)
    assert waiting["status"] == "WAITING_APPROVAL"
    assert waiting["protected"]["receipts"] == []
    assert p3_lab.runtime.active().snapshot().outbox_count == 0
    approve_pending(p3_lab)
    run = view(p3_lab, run_id)
    assert run["status"] == "COMPLETED"
    assert outbox(run["protected"]) == 1


def test_s06_rejection_sends_nothing(p3_lab) -> None:
    run_id = start(p3_lab, "S06")
    pending = p3_lab.client.get("/api/v1/approvals", params={"status": "PENDING"}).json()["items"][0]
    response = p3_lab.client.post(
        f"/api/v1/approvals/{pending['approval_id']}/reject",
        json={"expected_version": pending["row_version"], "reason": "No procede"},
        headers=p3_lab.login("approver"),
    )
    assert response.status_code == 200, response.text
    run = view(p3_lab, run_id)
    assert run["status"] == "COMPLETED"
    assert outbox(run["protected"]) == 0


def test_operator_cannot_approve_own_run(p3_lab) -> None:
    start(p3_lab, "S06")
    pending = p3_lab.client.get("/api/v1/approvals", params={"status": "PENDING"}).json()["items"][0]
    response = p3_lab.client.post(
        f"/api/v1/approvals/{pending['approval_id']}/approve",
        json={"expected_version": pending["row_version"], "reason": "Intento propio"},
        headers=p3_lab.login("operator"),
    )
    assert response.status_code == 403
    assert p3_lab.runtime.active().snapshot().outbox_count == 0


def test_s07_altered_body_is_blocked_with_no_new_effect(p3_lab) -> None:
    run = run_scenario(p3_lab, "S07")
    assert run["status"] == "COMPLETED", run
    assert "IDEMPOTENCY_CONFLICT" in run["protected"]["reason"]
    assert outbox(run["protected"]) == 1


def test_s08_injected_document_does_not_delete(p3_lab) -> None:
    run = run_scenario(p3_lab, "S08")
    assert decisions(run["protected"]) == ["ALLOW", "DENY"]
    assert records(run["baseline"]) == 7
    assert records(run["protected"]) == 8
    assert "determinista" in run["agent_kind_label"]


def test_s09_invalid_policy_leaves_active_policy_intact(p3_lab) -> None:
    active = p3_lab.app.state.person3_policy.get_active_snapshot().checksum
    run = run_scenario(p3_lab, "S09")
    assert run["status"] == "COMPLETED", run
    assert run["baseline"]["state"] == "NOT_APPLICABLE"
    assert "rechazado" in run["protected"]["reason"]
    assert p3_lab.app.state.person3_policy.get_active_snapshot().checksum == active


def test_s10_second_consumption_is_rejected(p3_lab) -> None:
    run = run_scenario(p3_lab, "S10")
    assert run["status"] == "COMPLETED", run
    assert "APPROVAL_ALREADY_CONSUMED" in run["protected"]["reason"]
    assert outbox(run["baseline"]) == 2
    assert outbox(run["protected"]) == 1


def test_all_ten_scenarios_fill_the_matrix_from_persisted_runs(p3_lab) -> None:
    for number in range(1, 11):
        # P3 limita a 10 logins por cliente cada 5 minutos, aunque sean correctos.
        with write_transaction(p3_lab.app.state.person3_engine) as connection:
            connection.execute(text("DELETE FROM login_rate_limits"))
        assert run_scenario(p3_lab, f"S{number:02d}")["status"] == "COMPLETED"
    items = p3_lab.client.get("/api/v1/matrix", params={"limit": 100}).json()["items"]
    assert sorted(item["scenario_id"] for item in items) == [f"S{number:02d}" for number in range(1, 11)]


class TestAuditConnected:
    def test_gateway_events_reach_the_chained_audit(self, p3_lab) -> None:
        run_scenario(p3_lab, "S04")
        items = p3_lab.client.get("/api/v1/audit", params={"event_type": "authorization_decided"}).json()["items"]
        assert len(items) == 1
        event = items[0]
        assert event["decision"] == "DENY"
        assert event["risk"] == "HIGH"
        assert event["reason_code"] == "RULE_DENY"
        assert event["tool"] == "record.delete"
        assert event["agent_id"] == "demo-agent"
        assert event["environment_id"] == "protected-fixture"
        assert event["policy_id"] == "demo-policy"

    def test_timeline_follows_a_request_through_approval_to_execution(self, p3_lab) -> None:
        run = run_scenario(p3_lab, "S06")
        request_id = run["protected"]["request_ids"][0]
        items = p3_lab.client.get("/api/v1/audit", params={"request_id": request_id}).json()["items"]
        kinds = [item["event_type"] for item in reversed(items)]
        assert kinds[:3] == ["request_received", "authorization_decided", "approval_created"]
        assert "approval_approved" in kinds
        assert "execution_completed" in kinds

    def test_dashboard_counts_real_events_and_denial_is_not_a_failure(self, p3_lab) -> None:
        run_scenario(p3_lab, "S01")
        run_scenario(p3_lab, "S04")
        body = p3_lab.client.get("/api/v1/dashboard").json()
        assert body["counters"]["decisions"] == 2
        assert body["by_decision"] == {"ALLOW": 1, "DENY": 1, "REQUIRE_APPROVAL": 0}
        assert body["counters"]["executions_completed"] == 1
        assert body["counters"]["executions_failed"] == 0

    def test_pending_approval_appears_on_dashboard_and_clears(self, p3_lab) -> None:
        start(p3_lab, "S06")
        assert p3_lab.client.get("/api/v1/dashboard").json()["counters"]["approvals_pending"] == 1
        approve_pending(p3_lab)
        assert p3_lab.client.get("/api/v1/dashboard").json()["counters"]["approvals_pending"] == 0

    def test_policy_activation_is_visible_with_the_published_checksum(self, p3_lab) -> None:
        p3_lab.login("viewer")
        items = p3_lab.client.get("/api/v1/audit", params={"event_type": "policy_activated"}).json()
        checksum = p3_lab.app.state.person3_policy.get_active_snapshot().checksum
        assert items["items"][0]["checksum"] == checksum

    def test_chain_stays_valid_across_all_producers(self, p3_lab) -> None:
        for scenario in ("S01", "S04", "S06", "S09"):
            run_scenario(p3_lab, scenario)
        with p3_lab.app.state.person3_engine.connect() as connection:
            report = verify_chain(connection)
            total = connection.execute(text("SELECT COUNT(*) FROM audit_events")).scalar_one()
        assert report.valid
        assert report.checked == total > 10

    def test_audit_failure_blocks_the_tool_call(self, p3_lab, monkeypatch) -> None:
        def broken(event, transaction):
            raise RuntimeError("disco lleno")

        headers = p3_lab.login("operator")
        monkeypatch.setattr(p3_lab.gateway.audit, "append", broken)
        response = p3_lab.client.post(
            "/api/v1/tool-requests",
            content=p3_lab.call("file.read").model_dump_json(),
            headers={**headers, "Idempotency-Key": "11111111-1111-4111-8111-111111111111", "Content-Type": "application/json"},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AUDIT_UNAVAILABLE"
        assert p3_lab.runtime.active().snapshot().journal_count == 0


def test_session_required_on_real_routes(p3_lab) -> None:
    p3_lab.client.cookies.clear()
    for path in ("/api/v1/audit", "/api/v1/dashboard", "/api/v1/matrix", "/api/v1/agents"):
        assert p3_lab.client.get(path).status_code == 401, path


def test_viewer_cannot_start_runs(p3_lab) -> None:
    response = p3_lab.client.post(
        RUNS, json={"scenario_id": "S01", "seed": 0, "mode": "paired"}, headers=p3_lab.login("viewer")
    )
    assert response.status_code == 403


class TestSeed:
    def test_users_get_random_passwords_and_are_idempotent(self, p3_lab) -> None:
        repository = p3_lab.app.state.person3_auth.repository
        created = seed_users(repository)
        assert set(created) == set(DEMO_USERS)
        assert len(set(created.values())) == len(created)
        assert all(len(password) >= 20 for password in created.values())
        assert seed_users(repository) == {}

    def test_policy_seed_does_not_replace_an_active_policy(self, p3_lab) -> None:
        assert seed_policy(p3_lab.settings.control_db_path) is None

    def test_seeded_user_can_log_in(self, p3_lab) -> None:
        created = seed_users(p3_lab.app.state.person3_auth.repository)
        response = p3_lab.client.post(
            "/api/v1/auth/login",
            json={"username": "demo-viewer", "password": created["demo-viewer"]},
            headers={"Origin": "http://127.0.0.1:8080"},
        )
        assert response.status_code == 200
