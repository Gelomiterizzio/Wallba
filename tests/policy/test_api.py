import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import FixedClock, RecordingAudit, deny_delete, policy_dict

from wallba.policy.repository import SqlitePolicyRepository
from wallba.policy.routes import PolicyActor, mount_policy_api
from wallba.policy.schemas import canonical_bytes, validate_mapping
from wallba.policy.service import PolicyService


def _actor(kind: str, roles: set[str], csrf_valid: bool) -> PolicyActor:
    return PolicyActor(
        principal_id="demo-policy-admin",
        kind=kind,
        roles=frozenset(roles),
        csrf_valid=csrf_valid,
    )


@pytest.fixture
def api(tmp_path):
    repository = SqlitePolicyRepository(tmp_path / "policy.sqlite")
    audit = RecordingAudit()
    service = PolicyService(repository, FixedClock(), audit)
    holder = {"actor": _actor("human", {"policy_admin", "viewer"}, True)}
    app = FastAPI()
    mount_policy_api(app, service, lambda: holder["actor"])
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, service=service, holder=holder, audit=audit)


def _document() -> dict[str, object]:
    report = validate_mapping(policy_dict([deny_delete()]))
    assert report.document is not None
    return json.loads(canonical_bytes(report.document))


def test_agent_and_viewer_cannot_activate_or_change_the_snapshot(api):
    created = api.client.post("/api/v1/policies/demo-policy/versions", json=_document())
    assert created.status_code == 201
    activated = api.client.post(
        "/api/v1/policies/demo-policy/activate",
        json={"version": 1, "expected_active_version": None},
    )
    assert activated.status_code == 200
    before = api.service.get_active_snapshot()
    assert before is not None

    api.holder["actor"] = _actor("agent", {"policy_admin", "viewer"}, True)
    agent = api.client.post(
        "/api/v1/policies/demo-policy/activate",
        json={"version": 1, "expected_active_version": 1},
    )
    assert agent.status_code == 403
    assert agent.json()["error"]["code"] == "FORBIDDEN"

    api.holder["actor"] = _actor("human", {"viewer"}, True)
    viewer = api.client.post(
        "/api/v1/policies/demo-policy/activate",
        json={"version": 1, "expected_active_version": 1},
    )
    assert viewer.status_code == 403
    listed = api.client.get("/api/v1/policies")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["active"] is True

    after = api.service.get_active_snapshot()
    assert after is not None
    assert after.checksum == before.checksum
    assert after.document.version == 1


def test_validate_does_not_publish_and_invalid_document_returns_422(api):
    before = api.service.list_versions(None, 50)
    response = api.client.post(
        "/api/v1/policies/validate",
        json={"format": "json", "content": json.dumps({"schema_version": "1", "priority": 1})},
    )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "POLICY_INVALID"
    assert any(item["field"] == "priority" and item["code"] == "unknown_field" for item in body["details"])
    assert api.service.list_versions(None, 50).items == before.items
    assert api.service.get_active_snapshot() is None


def test_missing_session_csrf_conflict_and_oversize_payload(api):
    api.holder["actor"] = None
    anonymous = api.client.get("/api/v1/policies")
    assert anonymous.status_code == 401

    api.holder["actor"] = _actor("human", {"policy_admin", "viewer"}, False)
    missing_csrf = api.client.post("/api/v1/policies/validate", json={"format": "yaml", "content": "[]"})
    assert missing_csrf.status_code == 403

    api.holder["actor"] = _actor("human", {"policy_admin", "viewer"}, True)
    oversized = api.client.post(
        "/api/v1/policies/validate",
        json={"format": "json", "content": "a" * 70000},
    )
    assert oversized.status_code == 413

    created = api.client.post("/api/v1/policies/demo-policy/versions", json=_document())
    assert created.status_code == 201
    again = api.client.post("/api/v1/policies/demo-policy/versions", json=_document())
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CONFLICT"
    stale = api.client.post(
        "/api/v1/policies/demo-policy/activate",
        json={"version": 1, "expected_active_version": 4},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STALE_POLICY"
    assert stale.headers["x-request-id"] == stale.json()["error"]["request_id"]
    assert api.service.get_active_snapshot() is None
    assert api.audit.events == []


def test_version_detail_pagination_and_missing_version(api):
    for version, rule_id in ((1, "deny-one"), (2, "deny-two"), (3, "deny-three")):
        document = _document()
        document["version"] = version
        document["rules"][0]["id"] = rule_id
        created = api.client.post("/api/v1/policies/demo-policy/versions", json=document)
        assert created.status_code == 201
    missing = api.client.get("/api/v1/policies/demo-policy/versions/9")
    assert missing.status_code == 404
    detail = api.client.get("/api/v1/policies/demo-policy/versions/1")
    assert detail.status_code == 200
    assert detail.json()["document"]["rules"][0]["id"] == "deny-one"
    assert detail.json()["active"] is False
    seen: list[int] = []
    cursor = None
    for _ in range(4):
        path = "/api/v1/policies?limit=1" if cursor is None else f"/api/v1/policies?limit=1&cursor={cursor}"
        page = api.client.get(path)
        assert page.status_code == 200
        body = page.json()
        seen.extend(item["version"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == [3, 2, 1]


def test_activation_audit_event_has_no_policy_body(api):
    created = api.client.post("/api/v1/policies/demo-policy/versions", json=_document())
    assert created.status_code == 201
    activated = api.client.post(
        "/api/v1/policies/demo-policy/activate",
        json={"version": 1, "expected_active_version": None},
    )
    assert activated.status_code == 200
    assert len(api.audit.events) == 1
    event = api.audit.events[0]
    assert set(event) == {"event_type", "policy_id", "policy_version", "checksum", "actor_id", "occurred_at"}
    assert event["event_type"] == "policy_activated"
    assert "rules" not in event
    assert "normalized_json" not in event
