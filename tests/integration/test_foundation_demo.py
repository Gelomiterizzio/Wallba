"""Integración del módulo P1 con dobles de P2/P3/P4 (WAL-P1-010, parcial).

Valida agente, runner, ejecutor y baseline reales de P1 de punta a punta. La integración
final exige gateway P3, motor P2 y AuditSink P4 reales: esto NO la sustituye.
"""

from __future__ import annotations

import re

import pytest
from conftest import OPERATOR, VIEWER

from wallba.demo.scenarios import SCENARIOS

DIRECT_SCENARIOS = [s.id for s in SCENARIOS if s.protected_plan == "gateway" and s.id != "S06"]


@pytest.mark.parametrize("scenario_id", DIRECT_SCENARIOS)
def test_scenario_runs_end_to_end_with_real_executors(lab, scenario_id: str) -> None:
    run_id = lab.client.post(
        "/api/v1/demo-runs",
        json={"scenario_id": scenario_id, "seed": 11, "mode": "paired"},
        headers=OPERATOR,
    ).json()["run_id"]
    run = lab.client.get(f"/api/v1/demo-runs/{run_id}", headers=VIEWER).json()
    assert run["status"] == "COMPLETED"
    assert run["evidence_id"]
    assert lab.client.get(f"/api/v1/demo-runs/{run_id}/evidence", headers=VIEWER).status_code == 200


def test_all_finished_runs_appear_once_in_matrix_with_reproducible_seed(lab) -> None:
    digests = []
    for _ in range(2):
        run_id = lab.client.post(
            "/api/v1/demo-runs", json={"scenario_id": "S04", "seed": 11, "mode": "paired"}, headers=OPERATOR
        ).json()["run_id"]
        digests.append(lab.client.get(f"/api/v1/demo-runs/{run_id}", headers=VIEWER).json()["fixture_digest"])
    assert digests[0] == digests[1]
    assert len(lab.client.get("/api/v1/matrix", headers=VIEWER).json()["items"]) == 2


def test_control_restart_preserves_runs_and_evidence(lab) -> None:
    run_id = lab.client.post(
        "/api/v1/demo-runs", json={"scenario_id": "S04", "seed": 11, "mode": "paired"}, headers=OPERATOR
    ).json()["run_id"]
    before = lab.client.get(f"/api/v1/demo-runs/{run_id}/evidence", headers=VIEWER).json()
    app = lab.client.app
    app.state.engine.dispose()
    after = lab.client.get(f"/api/v1/demo-runs/{run_id}/evidence", headers=VIEWER).json()
    assert before == after


def test_no_secret_leaks_through_public_responses(lab) -> None:
    run_id = lab.client.post(
        "/api/v1/demo-runs", json={"scenario_id": "S01", "seed": 11, "mode": "paired"}, headers=OPERATOR
    ).json()["run_id"]
    text = lab.client.get(f"/api/v1/demo-runs/{run_id}", headers=VIEWER).text
    assert not re.search("e{32}|b{32}|s{32}", text)
