"""Manifest y matriz: solo observaciones reales (WAL-P1-008)."""

from __future__ import annotations

import copy
from typing import Any

from conftest import OPERATOR, VIEWER

from wallba.demo.evidence import verify_manifest

RUNS = "/api/v1/demo-runs"
REQUIRED_MANIFEST_KEYS = {
    "schema_version",
    "git_sha",
    "runtime_versions",
    "scenario",
    "seed",
    "fixture_digest",
    "calls",
    "transcript_digest",
    "environments",
    "policy",
    "baseline",
    "protected",
    "audit_event_ids",
    "observed_assertions",
    "started_at",
    "completed_at",
    "expectations",
}


def _run(lab, scenario_id: str = "S04") -> str:
    response = lab.client.post(
        RUNS, json={"scenario_id": scenario_id, "seed": 7, "mode": "paired"}, headers=OPERATOR
    )
    return response.json()["run_id"]


def _evidence(lab, run_id: str) -> dict[str, Any]:
    return lab.client.get(f"{RUNS}/{run_id}/evidence", headers=VIEWER).json()


def test_matrix_is_empty_before_any_run(lab) -> None:
    assert lab.client.get("/api/v1/matrix", headers=VIEWER).json() == {"items": [], "next_cursor": None}


def test_scenario_catalog_does_not_fill_the_matrix(lab) -> None:
    assert len(lab.client.get("/api/v1/scenarios", headers=VIEWER).json()["items"]) == 10
    assert lab.client.get("/api/v1/matrix", headers=VIEWER).json()["items"] == []


def test_matrix_row_comes_from_persisted_run(lab) -> None:
    run_id = _run(lab)
    items = lab.client.get("/api/v1/matrix", headers=VIEWER).json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["run_id"] == run_id
    assert row["protected_decision"] == "DENY"
    assert row["protected_reason_code"] == "RULE_DENY"
    assert row["baseline_effect_count"] == 1
    assert row["protected_effect_count"] == 0
    assert row["evidence_id"]


def test_waiting_run_is_not_in_matrix(lab) -> None:
    _run(lab, "S06")
    assert lab.client.get("/api/v1/matrix", headers=VIEWER).json()["items"] == []


def test_matrix_filter_by_scenario(lab) -> None:
    _run(lab, "S04")
    assert lab.client.get("/api/v1/matrix", params={"scenario_id": "S01"}, headers=VIEWER).json()["items"] == []
    assert lab.client.get("/api/v1/matrix", params={"scenario_id": "S99"}, headers=VIEWER).status_code == 422


def test_manifest_has_required_fields_and_valid_digest(lab) -> None:
    evidence = _evidence(lab, _run(lab))
    assert REQUIRED_MANIFEST_KEYS <= set(evidence["manifest"])
    assert verify_manifest(evidence["manifest"], evidence["manifest_digest"])


def test_altered_manifest_fails_digest(lab) -> None:
    evidence = _evidence(lab, _run(lab))
    altered = copy.deepcopy(evidence["manifest"])
    altered["protected"]["state"] = "OBSERVED-ALTERADO"
    assert not verify_manifest(altered, evidence["manifest_digest"])


def test_observed_assertions_reflect_real_state(lab) -> None:
    assertions = _evidence(lab, _run(lab))["manifest"]["observed_assertions"]
    assert assertions["baseline"] == {
        "state_changed": True,
        "records_removed": 1,
        "outbox_added": 0,
        "journal_added": 1,
    }
    assert assertions["protected"] == {
        "state_changed": False,
        "records_removed": 0,
        "outbox_added": 0,
        "journal_added": 0,
    }


def test_expectations_are_separated_and_labeled(lab) -> None:
    manifest = _evidence(lab, _run(lab))["manifest"]
    assert manifest["expectations"]["label"] == "EXPECTATION"
    assert "expectation" not in str(manifest["observed_assertions"]).lower()


def test_email_body_is_redacted_from_manifest(lab) -> None:
    manifest = _evidence(lab, _run(lab, "S05"))["manifest"]
    parameters = manifest["calls"][0]["call"]["parameters"]
    assert "body" not in parameters
    assert parameters["body_digest"]


def test_manifest_has_no_secrets(lab) -> None:
    text = str(_evidence(lab, _run(lab))["manifest"])
    assert "e" * 32 not in text
    assert "b" * 32 not in text


def test_partial_evidence_has_null_assertions_instead_of_inventing(lab, monkeypatch) -> None:
    import httpx

    def down(*args, **kwargs):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(lab.executor_client, "request", down)
    manifest = _evidence(lab, _run(lab))["manifest"]
    assert manifest["observed_assertions"]["protected"]["state_changed"] is None
    assert manifest["protected"]["state"] == "INCOMPLETE"


def test_audit_receives_demo_events_without_writing_tables(lab) -> None:
    run_id = _run(lab)
    types = [event.event_type for event in lab.audit.events if event.run_id == run_id]
    assert types == ["demo_started", "demo_completed"]
    manifest = _evidence(lab, run_id)["manifest"]
    assert len(manifest["audit_event_ids"]) == 2


def test_git_sha_null_declares_reason(lab, monkeypatch) -> None:
    monkeypatch.delenv("WALLBA_GIT_SHA", raising=False)
    manifest = _evidence(lab, _run(lab))["manifest"]
    assert manifest["git_sha"] is None
    assert manifest["git_sha_null_reason"]
