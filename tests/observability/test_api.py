"""API de auditoría, dashboard y exportación (WAL-P4-004)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import LOOPBACK, OPERATOR, VIEWER
from fastapi.testclient import TestClient
from sqlalchemy import text
from support.fakes import FakeAuthorizer

from wallba.contracts.canonical import canonical_json, sha256_hex
from wallba.contracts.ports import AuditEventDraft
from wallba.demo.environments import HttpEnvironment
from wallba.foundation.app import create_app
from wallba.foundation.config import Settings
from wallba.foundation.database import write_transaction
from wallba.foundation.http import Integrations
from wallba.observability.router import router as observability_router
from wallba.observability.writer import AuditWriter

T0 = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
REQUEST_A = "11111111-1111-4111-8111-111111111111"
REQUEST_B = "22222222-2222-4222-8222-222222222222"
RUN = "33333333-3333-4333-8333-333333333333"


class StepClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        current = self.now
        self.now += timedelta(seconds=10)
        return current


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        role="control",
        environment_id="protected-fixture",
        data_dir=tmp_path,
        executor_url="http://executor",
        executor_token="t" * 32,
    )
    integrations = Integrations(authorizer=FakeAuthorizer(), extra_routers=[observability_router])
    environment = HttpEnvironment("http://executor", "t", client=object())
    with TestClient(create_app(settings, integrations, protected_env=environment), client=LOOPBACK) as value:
        yield value


def write(client: TestClient, *drafts: AuditEventDraft) -> list[str]:
    writer = AuditWriter(clock=StepClock())
    ids = []
    with write_transaction(client.app.state.engine) as connection:
        last = connection.execute(text("SELECT COUNT(*) FROM audit_events")).scalar_one()
        writer._clock.now = T0 + timedelta(seconds=10 * last)  # noqa: SLF001
        for draft in drafts:
            ids.append(writer.append(draft, connection))
    return ids


def decided(request_id: str, decision: str, risk: str, tool: str = "record.delete", **extra) -> AuditEventDraft:
    return AuditEventDraft(
        event_type="authorization_decided",
        request_id=request_id,
        decision=decision,
        risk=risk,
        tool=tool,
        agent_id="demo-agent",
        environment_id="protected-fixture",
        reason_code="RULE_DENY" if decision == "DENY" else "RULE_ALLOW",
        **extra,
    )


@pytest.fixture
def seeded(client: TestClient) -> list[str]:
    return write(
        client,
        AuditEventDraft(event_type="request_received", request_id=REQUEST_A, environment_id="protected-fixture"),
        decided(REQUEST_A, "DENY", "HIGH"),
        decided(REQUEST_B, "ALLOW", "LOW", tool="file.read"),
        AuditEventDraft(event_type="execution_completed", request_id=REQUEST_B, environment_id="protected-fixture"),
        AuditEventDraft(event_type="execution_failed", request_id=REQUEST_B, environment_id="protected-fixture"),
        AuditEventDraft(event_type="approval_created", request_id=REQUEST_B),
        AuditEventDraft(event_type="approval_created", request_id=REQUEST_A),
        AuditEventDraft(event_type="approval_approved", request_id=REQUEST_A),
        AuditEventDraft(event_type="demo_started", run_id=RUN, principal_id="demo-operator"),
        AuditEventDraft(event_type="execution_completed", environment_id="baseline-fixture"),
    )


def audit(client: TestClient, **params) -> dict:
    response = client.get("/api/v1/audit", params=params, headers=VIEWER)
    assert response.status_code == 200, response.text
    return response.json()


class TestAuthorization:
    @pytest.mark.parametrize(
        "path",
        ["/api/v1/audit", "/api/v1/dashboard", f"/api/v1/audit/{REQUEST_A}", "/api/v1/audit/export?from=2026-01-01T00:00:00Z&to=2026-01-02T00:00:00Z"],
    )
    def test_requires_identity_and_viewer_role(self, client: TestClient, path: str) -> None:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=OPERATOR).status_code == 403

    def test_fails_closed_without_authorizer(self, tmp_path: Path) -> None:
        settings = Settings(
            role="control",
            environment_id="protected-fixture",
            data_dir=tmp_path,
            executor_url="http://executor",
            executor_token="t" * 32,
        )
        app = create_app(
            settings,
            Integrations(extra_routers=[observability_router]),
            protected_env=HttpEnvironment("http://x", "t", client=object()),
        )
        with TestClient(app) as client:
            response = client.get("/api/v1/audit", headers=VIEWER)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AUTHORIZATION_UNAVAILABLE"

    def test_there_are_no_mutation_routes(self, client: TestClient) -> None:
        methods = {
            method
            for route in client.app.routes
            if getattr(route, "path", "").startswith(("/api/v1/audit", "/api/v1/dashboard"))
            for method in route.methods
        }
        assert methods <= {"GET", "HEAD"}


class TestAuditList:
    def test_newest_first_and_null_fields_not_invented(self, client: TestClient, seeded: list[str]) -> None:
        items = audit(client)["items"]
        assert items[0]["sequence"] == 10
        admin = next(item for item in items if item["event_type"] == "demo_started")
        assert admin["request_id"] is None
        assert admin["request_digest"] is None

    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            ({"decision": "DENY"}, 1),
            ({"risk": "LOW"}, 1),
            ({"tool": "file.read"}, 1),
            ({"agent_id": "demo-agent"}, 2),
            ({"request_id": REQUEST_A}, 4),
            ({"run_id": RUN}, 1),
            ({"event_type": "approval_created"}, 2),
            ({"q": RUN}, 1),
            ({"q": "RULE_DENY"}, 1),
            ({"q": "' OR 1=1 --"}, 0),
            ({"q": "%"}, 0),
        ],
    )
    def test_filters(self, client: TestClient, seeded: list[str], params: dict, expected: int) -> None:
        assert len(audit(client, **params)["items"]) == expected

    def test_time_window_is_inclusive_from_and_exclusive_to(self, client: TestClient, seeded: list[str]) -> None:
        window = {"from": (T0 + timedelta(seconds=10)).isoformat(), "to": (T0 + timedelta(seconds=30)).isoformat()}
        assert [item["sequence"] for item in audit(client, **window)["items"]] == [3, 2]

    def test_non_utc_offsets_are_converted(self, client: TestClient, seeded: list[str]) -> None:
        offset = timezone(timedelta(hours=-4))
        start = (T0 + timedelta(seconds=10)).astimezone(offset).isoformat()
        end = (T0 + timedelta(seconds=30)).astimezone(offset).isoformat()
        assert len(audit(client, **{"from": start, "to": end})["items"]) == 2

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 0},
            {"limit": 101},
            {"decision": "MAYBE"},
            {"tool": "shell.exec"},
            {"request_id": "x"},
            {"from": "2026-10-31T12:00:00"},
            {"desconocido": "1"},
            {"sort": "event_hash; DROP TABLE audit_events"},
            {"cursor": "%%%"},
            {"cursor": "YWJj"},
        ],
    )
    def test_invalid_query_is_422(self, client: TestClient, params: dict) -> None:
        response = client.get("/api/v1/audit", params=params, headers=VIEWER)
        assert response.status_code == 422
        assert set(response.json()["error"]) == {"code", "message", "request_id", "details"}

    def test_pagination_has_no_repeats_or_gaps_even_with_new_events(
        self, client: TestClient, seeded: list[str]
    ) -> None:
        first = audit(client, limit=4)
        write(client, AuditEventDraft(event_type="demo_completed"))
        second = audit(client, limit=4, cursor=first["next_cursor"])
        third = audit(client, limit=4, cursor=second["next_cursor"])
        seen = [item["sequence"] for page in (first, second, third) for item in page["items"]]
        assert seen == [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
        assert third["next_cursor"] is None

    def test_empty_result_is_a_real_empty_page(self, client: TestClient) -> None:
        assert audit(client) == {"items": [], "next_cursor": None}


class TestDetail:
    def test_detail_reports_verified_integrity_and_limitation(self, client: TestClient, seeded: list[str]) -> None:
        body = client.get(f"/api/v1/audit/{seeded[1]}", headers=VIEWER).json()
        assert body["event"]["decision"] == "DENY"
        assert body["integrity"]["verified"] is True
        assert body["integrity"]["checked_events"] == 2
        assert "administra el host" in body["integrity"]["limitation"]

    def test_detail_reports_tampering(self, client: TestClient, seeded: list[str]) -> None:
        with write_transaction(client.app.state.engine) as connection:
            connection.execute(text("DROP TRIGGER audit_events_no_update"))
            connection.execute(text("UPDATE audit_events SET decision = 'ALLOW' WHERE sequence = 2"))
        body = client.get(f"/api/v1/audit/{seeded[3]}", headers=VIEWER).json()
        assert body["integrity"]["verified"] is False
        assert body["integrity"]["first_invalid_sequence"] == 2

    def test_unknown_and_invalid_ids(self, client: TestClient) -> None:
        assert client.get(f"/api/v1/audit/{REQUEST_A}", headers=VIEWER).status_code == 404
        assert client.get("/api/v1/audit/no-uuid", headers=VIEWER).status_code == 422


class TestDashboard:
    def test_empty_dashboard_returns_real_zeros(self, client: TestClient) -> None:
        body = client.get("/api/v1/dashboard", headers=VIEWER).json()
        assert set(body["counters"].values()) == {0}
        assert body["recent"] == []
        assert body["as_of"]

    def test_denial_is_not_a_failed_execution(self, client: TestClient) -> None:
        write(client, decided(REQUEST_A, "DENY", "HIGH"))
        counters = client.get("/api/v1/dashboard", headers=VIEWER).json()["counters"]
        assert counters["decisions"] == 1
        assert counters["executions_failed"] == 0

    def test_counters_exclude_baseline_by_default(self, client: TestClient, seeded: list[str]) -> None:
        body = client.get("/api/v1/dashboard", headers=VIEWER).json()
        assert body["counters"] == {
            "events": 9,
            "requests": 1,
            "decisions": 2,
            "executions_completed": 1,
            "executions_failed": 1,
            "executions_unknown": 0,
            "approvals_pending": 1,
        }
        assert body["by_decision"] == {"ALLOW": 1, "DENY": 1, "REQUIRE_APPROVAL": 0}
        assert body["by_risk"] == {"LOW": 1, "MEDIUM": 0, "HIGH": 1, "CRITICAL": 0}
        assert "baseline-fixture" not in [item.get("environment_id") for item in body["recent"]]

    def test_baseline_requires_explicit_filter(self, client: TestClient, seeded: list[str]) -> None:
        body = client.get("/api/v1/dashboard", params={"include_baseline": "true"}, headers=VIEWER).json()
        assert body["include_baseline"] is True
        assert body["counters"]["executions_completed"] == 2

    def test_totals_match_audit_table_in_same_window(self, client: TestClient, seeded: list[str]) -> None:
        window = {"from": T0.isoformat(), "to": (T0 + timedelta(seconds=40)).isoformat()}
        dashboard = client.get("/api/v1/dashboard", params=window, headers=VIEWER).json()
        table = audit(client, **window, event_type="authorization_decided", limit=100)["items"]
        assert dashboard["counters"]["decisions"] == len(table)
        assert dashboard["by_decision"]["DENY"] == sum(item["decision"] == "DENY" for item in table)
        assert dashboard["window_from"].startswith("2026-10-31T12:00:00")

    def test_unknown_filter_rejected(self, client: TestClient) -> None:
        assert client.get("/api/v1/dashboard", params={"x": "1"}, headers=VIEWER).status_code == 422


class TestExport:
    WINDOW = {"from": T0.isoformat(), "to": (T0 + timedelta(hours=1)).isoformat()}

    def _export(self, client: TestClient, **params):
        return client.get("/api/v1/audit/export", params={**self.WINDOW, **params}, headers=VIEWER)

    def test_range_is_required(self, client: TestClient) -> None:
        assert client.get("/api/v1/audit/export", headers=VIEWER).status_code == 422
        assert client.get("/api/v1/audit/export", params={"from": T0.isoformat()}, headers=VIEWER).status_code == 422

    def test_jsonl_manifest_digests_are_verifiable(self, client: TestClient, seeded: list[str]) -> None:
        response = self._export(client)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        lines = response.content.strip().split(b"\n")
        assert len(lines) == 11
        manifest = json.loads(lines[-1])
        assert manifest["type"] == "manifest"
        assert manifest["count"] == 10
        assert manifest["chain_valid"] is True
        assert manifest["events_digest"] == sha256_hex(b"\n".join(lines[:-1]))
        assert response.headers["x-wallba-manifest-digest"] == sha256_hex(lines[-1])
        assert lines[-1] == canonical_json(manifest)
        assert "host" in manifest["limitation"]

    def test_export_keeps_same_ids_as_listing(self, client: TestClient, seeded: list[str]) -> None:
        lines = self._export(client, request_id=REQUEST_A).content.strip().split(b"\n")
        exported = {json.loads(line)["event_id"] for line in lines[:-1]}
        listed = {item["event_id"] for item in audit(client, request_id=REQUEST_A)["items"]}
        assert exported == listed and len(exported) == 4

    def test_empty_range_produces_manifest_only(self, client: TestClient) -> None:
        lines = self._export(client).content.strip().split(b"\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["count"] == 0

    def test_too_many_events_is_rejected(self, client: TestClient, monkeypatch) -> None:
        import wallba.observability.exports as exports

        monkeypatch.setattr(exports, "MAX_EXPORT_EVENTS", 2)
        write(client, *[decided(REQUEST_A, "DENY", "HIGH") for _ in range(3)])
        response = self._export(client)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "EXPORT_TOO_LARGE"


def test_list_latency_with_ten_thousand_events(client: TestClient, capsys) -> None:
    """Objetivo p95 < 500 ms. Es una medición en este equipo, no un resultado certificado."""
    writer = AuditWriter(clock=StepClock())
    with write_transaction(client.app.state.engine) as connection:
        for _ in range(10_000):
            writer.append(decided(REQUEST_A, "DENY", "HIGH"), connection)
    samples = []
    for params in ({}, {"decision": "DENY"}, {"request_id": REQUEST_A}) * 7:
        started = time.perf_counter()
        assert client.get("/api/v1/audit", params=params, headers=VIEWER).status_code == 200
        samples.append(time.perf_counter() - started)
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    with capsys.disabled():
        print(f"\n[audit] GET /audit p95={p95 * 1000:.1f} ms con 10000 eventos")
    assert p95 < 0.5
