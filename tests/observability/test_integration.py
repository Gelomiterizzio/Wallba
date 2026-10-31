"""AuditWriter real conectado a sus productores: runner de P1 y políticas de P2.

Sigue usando FakeGateway y FakeAuthorizer: no es evidencia de protección de punta a punta.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import LOOPBACK, OPERATOR, VIEWER, baseline_settings, executor_settings
from fastapi.testclient import TestClient
from sqlalchemy import text
from support.fakes import (
    BASELINE_TOKEN,
    CAPABILITY_SECRET,
    ENVIRONMENT_ID,
    EXECUTOR_TOKEN,
    KEY_ID,
    FakeAuthorizer,
    FakeGateway,
)

from wallba.agent.scripted import ScriptedAgent
from wallba.contracts.decision import DecisionEnvelope
from wallba.demo.environments import HttpEnvironment
from wallba.executor.app import create_executor_app
from wallba.executor.runtime import ExecutorRuntime
from wallba.foundation.app import control_integrations, create_app
from wallba.foundation.config import Settings
from wallba.foundation.database import create_sqlite_engine, run_migrations
from wallba.foundation.http import Integrations
from wallba.observability.adapters import PolicyAuditSink
from wallba.observability.router import router as observability_router
from wallba.observability.writer import AuditWriter, verify_chain
from wallba.policy.evaluator import evaluate
from wallba.policy.loader import load_policy
from wallba.policy.models import TrustedContext
from wallba.policy.repository import SqlitePolicyRepository
from wallba.policy.schemas import snapshot_from_document, validate_mapping
from wallba.policy.service import PolicyService, PolicyUnavailable

ROOT = Path(__file__).resolve().parents[2]
POLICY = load_policy((ROOT / "policies" / "demo.yaml").read_bytes(), "yaml").document


@pytest.fixture
def lab(tmp_path: Path) -> Iterator[TestClient]:
    protected = ExecutorRuntime(tmp_path / "protected" / "sandboxes", "executor")
    baseline = ExecutorRuntime(tmp_path / "baseline" / "sandboxes", "baseline")
    executor_app = create_executor_app(executor_settings(tmp_path / "protected"), protected)
    baseline_app = create_executor_app(baseline_settings(tmp_path / "baseline"), baseline)
    with TestClient(executor_app) as executor_client, TestClient(baseline_app) as baseline_client:
        settings = Settings(
            role="control",
            environment_id=ENVIRONMENT_ID,
            demo_enabled=True,
            data_dir=tmp_path / "control",
            capability_key_id=KEY_ID,
            capability_secret=CAPABILITY_SECRET,
            executor_url="http://executor",
            baseline_url="http://baseline",
            executor_token=EXECUTOR_TOKEN,
            baseline_token=BASELINE_TOKEN,
        )
        integrations = Integrations(
            authorizer=FakeAuthorizer(),
            gateway=FakeGateway(executor_client),
            audit=AuditWriter(),
            extra_routers=[observability_router],
        )
        app = create_app(
            settings,
            integrations,
            protected_env=HttpEnvironment("", EXECUTOR_TOKEN, client=executor_client),
            baseline_env=HttpEnvironment("", BASELINE_TOKEN, client=baseline_client),
        )
        with TestClient(app, client=LOOPBACK) as client:
            yield client
    protected.sandboxes.dispose()
    baseline.sandboxes.dispose()


def test_demo_run_writes_verifiable_events_queryable_by_run_id(lab: TestClient) -> None:
    run_id = lab.post(
        "/api/v1/demo-runs", json={"scenario_id": "S04", "seed": 7, "mode": "paired"}, headers=OPERATOR
    ).json()["run_id"]

    items = lab.get("/api/v1/audit", params={"run_id": run_id}, headers=VIEWER).json()["items"]
    assert [item["event_type"] for item in items] == ["demo_completed", "demo_started"]

    manifest = lab.get(f"/api/v1/demo-runs/{run_id}/evidence", headers=VIEWER).json()["manifest"]
    assert sorted(manifest["audit_event_ids"]) == sorted(item["event_id"] for item in items)
    assert items[0]["evidence_id"] == manifest["evidence_id"]

    detail = lab.get(f"/api/v1/audit/{items[0]['event_id']}", headers=VIEWER).json()
    assert detail["integrity"]["verified"] is True
    with lab.app.state.engine.connect() as connection:
        assert verify_chain(connection).valid


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def policy_db(tmp_path: Path) -> Path:
    path = tmp_path / "control.sqlite"
    run_migrations(path)
    return path


def test_policy_tables_come_from_the_shared_migration(policy_db: Path) -> None:
    engine = create_sqlite_engine(policy_db)
    with engine.connect() as connection:
        names = connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'")).scalars().all()
    engine.dispose()
    assert {"policy_versions", "policy_activation", "audit_events"} <= set(names)


def test_policy_activation_is_audited_in_the_same_chain(policy_db: Path) -> None:
    repository = SqlitePolicyRepository(policy_db)
    service = PolicyService(repository, _Clock(), PolicyAuditSink(AuditWriter()))
    repository.save_version(POLICY, "demo-policy-admin", "2026-10-31T12:00:00Z")
    snapshot = service.activate("demo-policy", POLICY.version, None, "demo-policy-admin")

    engine = create_sqlite_engine(policy_db)
    with engine.connect() as connection:
        assert verify_chain(connection).valid
        fields = connection.execute(text("SELECT fields_json FROM audit_events")).scalar_one()
    engine.dispose()
    # P4 enseña el mismo checksum que publica P2.
    assert snapshot.checksum in fields
    assert "demo-policy-admin" in fields


def test_audit_failure_rolls_back_policy_activation(policy_db: Path) -> None:
    class BrokenWriter(AuditWriter):
        def append(self, event, transaction):
            raise RuntimeError("disco lleno")

    repository = SqlitePolicyRepository(policy_db)
    service = PolicyService(repository, _Clock(), PolicyAuditSink(BrokenWriter()))
    repository.save_version(POLICY, "demo-policy-admin", "2026-10-31T12:00:00Z")
    with pytest.raises(PolicyUnavailable) as error:
        service.activate("demo-policy", POLICY.version, None, "demo-policy-admin")
    assert error.value.code == "AUDIT_UNAVAILABLE"
    assert repository.get_active_snapshot() is None


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("S01", ["ALLOW"]),
        ("S02", ["DENY"]),
        ("S03", ["ALLOW"]),
        ("S04", ["DENY"]),
        ("S05", ["DENY"]),
        ("S06", ["REQUIRE_APPROVAL"]),
        ("S08", ["ALLOW", "DENY"]),
    ],
)
def test_real_policy_engine_decides_scripted_calls_as_designed(scenario: str, expected: list[str]) -> None:
    """Motor real de P2 con las llamadas reales del agente. Aún no pasa por el gateway de P3."""
    snapshot = snapshot_from_document(validate_mapping(POLICY.model_dump(mode="json", by_alias=True, exclude_none=True)).document)
    context = TrustedContext(
        principal_id="demo-operator",
        agent_id="demo-agent",
        roles=["operator"],
        environment_id=ENVIRONMENT_ID,
        server_time=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
        resource_version="1",
    )
    decisions = []
    for call in ScriptedAgent("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 7).plan(scenario):
        result = evaluate(call.model_dump(mode="json"), context, snapshot)
        # El resultado de P2 debe caber en el contrato compartido sin adaptaciones.
        decisions.append(DecisionEnvelope.model_validate_json(result.model_dump_json()).decision)
    assert decisions == expected


def test_control_integrations_expose_audit_and_real_policy_probe(tmp_path: Path) -> None:
    settings = Settings(
        role="control",
        environment_id=ENVIRONMENT_ID,
        data_dir=tmp_path,
        executor_url="http://executor",
        executor_token="t" * 32,
    )
    integrations = control_integrations(settings)
    assert isinstance(integrations.audit, AuditWriter)
    assert integrations.authorizer is None and integrations.gateway is None
    run_migrations(settings.control_db_path)
    assert integrations.policy_ready() is False
    repository = SqlitePolicyRepository(settings.control_db_path)
    repository.save_version(POLICY, "demo-policy-admin", "2026-10-31T12:00:00Z")
    PolicyService(repository, _Clock(), PolicyAuditSink(AuditWriter())).activate(
        "demo-policy", POLICY.version, None, "demo-policy-admin"
    )
    assert integrations.policy_ready() is True
