"""Los datos de ejemplo de MSW cumplen los mismos DTO estrictos que el servidor (WAL-P4-002)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from wallba.contracts.api import AgentDetail, DemoRunView, EvidenceView, MatrixRow, ScenarioView
from wallba.observability.schemas import AuditEventView, DashboardView, IntegrityView

FIXTURES: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[2] / "frontend" / "src" / "mocks" / "fixtures.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    ("key", "model"),
    [
        ("agents", AgentDetail),
        ("scenarios", ScenarioView),
        ("auditEvents", AuditEventView),
        ("matrix", MatrixRow),
    ],
)
def test_lists_follow_contract(key: str, model: Any) -> None:
    assert FIXTURES[key]
    for item in FIXTURES[key]:
        model.model_validate_json(json.dumps(item))


@pytest.mark.parametrize(("key", "model"), [("dashboard", DashboardView), ("evidence", EvidenceView), ("integrity", IntegrityView)])
def test_objects_follow_contract(key: str, model: Any) -> None:
    model.model_validate_json(json.dumps(FIXTURES[key]))


@pytest.mark.parametrize("name", ["S01", "S04", "S06", "UNKNOWN"])
def test_demo_runs_follow_contract(name: str) -> None:
    DemoRunView.model_validate_json(json.dumps(FIXTURES["demoRuns"][name]))


def test_scenarios_match_the_real_catalog() -> None:
    from wallba.demo.scenarios import SCENARIOS

    assert FIXTURES["scenarios"] == [scenario.view().model_dump(mode="json") for scenario in SCENARIOS]


def test_fixtures_have_no_real_looking_secrets() -> None:
    text = json.dumps(FIXTURES).lower()
    for term in ("password", "bearer ", "@gmail", "smtp"):
        assert term not in text
