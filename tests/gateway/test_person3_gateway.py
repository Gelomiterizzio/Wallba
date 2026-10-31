import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from wallba.approvals.models import approvals
from wallba.auth.models import AgentCredentialRecord, Scope
from wallba.auth.schema import principals
from wallba.auth.tokens import hash_opaque_token
from wallba.foundation.database import write_transaction
from wallba.foundation.http import ApiError
from wallba.gateway.schema import events, executions

ORIGIN = "http://127.0.0.1:8080"


def pending(lab, principal="operator"):
    call = lab.call()
    view = lab.gateway.submit(call, lab.principal(principal), str(uuid4()))
    assert view.state == "PENDING_APPROVAL"
    return call, view


def test_real_allow_deny_and_audit(p3_lab):
    lab = p3_lab
    allowed = lab.gateway.submit(lab.call("file.read"), lab.principal(), str(uuid4()))
    assert allowed.state == "SUCCEEDED" and allowed.receipt.effect_count == 0
    denied = lab.gateway.submit(
        lab.call("record.delete"), lab.principal(), str(uuid4())
    )
    assert denied.state == "DENIED" and denied.execution_id is None
    with lab.gateway.engine.connect() as c:
        assert (
            c.execute(
                select(executions).where(executions.c.request_id == denied.request_id)
            ).first()
            is None
        )
        names = (
            c.execute(
                select(events.c.event_type).where(
                    events.c.request_id == denied.request_id
                )
            )
            .scalars()
            .all()
        )
        assert names == ["request_received", "authorization_decided"]
    assert lab.runtime.active().snapshot().record_count == 8


def test_idempotency_survives_resource_version_change(p3_lab):
    lab = p3_lab
    call = lab.call()
    key = str(uuid4())
    first = lab.gateway.submit(call, lab.principal(), key)
    detail = lab.approvals.resolve(
        first.approval_id,
        lab.principal("approver"),
        "approve",
        1,
        "Operación sintética revisada",
    )
    assert detail["request_state"] == "SUCCEEDED"
    repeated = lab.gateway.submit(call, lab.principal(), key)
    assert (
        repeated.state == "SUCCEEDED"
        and repeated.execution_id == detail["execution_id"]
    )
    changed = call.model_copy(
        update={"parameters": call.parameters.model_copy(update={"body": "alterado"})}
    )
    with pytest.raises(ApiError) as e:
        lab.gateway.submit(changed, lab.principal(), key)
    assert e.value.code == "IDEMPOTENCY_CONFLICT"
    assert lab.runtime.active().snapshot().outbox_count == 1


def test_concurrent_submit_single_claim(p3_lab):
    lab = p3_lab
    call, key = lab.call("file.read"), str(uuid4())
    with ThreadPoolExecutor(max_workers=8) as pool:
        views = list(
            pool.map(
                lambda _: lab.gateway.submit(call, lab.principal(), key), range(12)
            )
        )
    assert len({view.execution_id for view in views}) == 1
    with lab.gateway.engine.connect() as c:
        assert len(c.execute(select(executions)).all()) == 1


def test_two_approvers_one_consumption(p3_lab):
    lab = p3_lab
    _, view = pending(lab)

    def attempt(_):
        try:
            return lab.approvals.resolve(
                view.approval_id,
                lab.principal("approver"),
                "approve",
                1,
                "Revisión concurrente",
            )
        except ApiError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert all(
        isinstance(result, dict) or result.status_code == 409 for result in results
    )
    assert lab.runtime.active().snapshot().outbox_count == 1


@pytest.mark.parametrize(
    "action,state", [("reject", "REJECTED"), ("cancel", "CANCELLED")]
)
def test_reject_cancel_and_terminal_state(p3_lab, action, state):
    lab = p3_lab
    _, view = pending(lab)
    actor = lab.principal("approver") if action == "reject" else lab.principal()
    detail = lab.approvals.resolve(view.approval_id, actor, action, 1, "No procede")
    assert detail["status"] == state and detail["execution_id"] is None
    with pytest.raises(ApiError):
        lab.approvals.resolve(
            view.approval_id,
            lab.principal("approver"),
            "approve",
            detail["row_version"],
            "Reintento",
        )
    assert lab.runtime.active().snapshot().outbox_count == 0


def test_no_self_approval_even_with_both_roles(p3_lab):
    lab = p3_lab
    _, view = pending(lab, "both")
    with pytest.raises(ApiError) as e:
        lab.approvals.resolve(
            view.approval_id, lab.principal("both"), "approve", 1, "No permitido"
        )
    assert e.value.code == "SELF_APPROVAL_DENIED"
    assert lab.runtime.active().snapshot().outbox_count == 0


def test_expiry_at_boundary_commits_without_timer(p3_lab):
    lab = p3_lab
    _, view = pending(lab)
    lab.clock.instant += timedelta(minutes=5)
    with pytest.raises(ApiError) as e:
        lab.approvals.resolve(
            view.approval_id, lab.principal("approver"), "approve", 1, "Demasiado tarde"
        )
    assert e.value.status_code == 410
    assert (
        lab.approvals.get(view.approval_id, lab.principal("viewer"))["status"]
        == "EXPIRED"
    )
    assert lab.runtime.active().snapshot().outbox_count == 0


def test_policy_change_invalidates_approval(p3_lab):
    lab = p3_lab
    _, view = pending(lab)
    data = {**lab.policy_data, "version": 2}
    lab.app.state.person3_policy.create_version(
        "demo-policy", json.dumps(data).encode(), "p3-admin"
    )
    lab.app.state.person3_policy.activate("demo-policy", 2, 1, "p3-admin")
    with pytest.raises(ApiError) as e:
        lab.approvals.resolve(
            view.approval_id,
            lab.principal("approver"),
            "approve",
            1,
            "Política diferente",
        )
    assert e.value.code == "STALE_POLICY"
    assert lab.runtime.active().snapshot().outbox_count == 0


def test_mutated_snapshot_blocked(p3_lab):
    lab = p3_lab
    _, view = pending(lab)
    with write_transaction(lab.gateway.engine) as c:
        ap = (
            c.execute(
                select(approvals).where(approvals.c.approval_id == view.approval_id)
            )
            .mappings()
            .one()
        )
        altered = json.loads(json.dumps(ap["snapshot_json"]))
        altered["call"]["parameters"]["body"] = "manipulado"
        c.execute(
            update(approvals)
            .where(approvals.c.approval_id == view.approval_id)
            .values(snapshot_json=altered)
        )
    with pytest.raises(ApiError) as e:
        lab.approvals.resolve(
            view.approval_id,
            lab.principal("approver"),
            "approve",
            1,
            "Intento manipulado",
        )
    assert e.value.code == "DIGEST_MISMATCH"
    assert lab.runtime.active().snapshot().outbox_count == 0


def test_revoked_requester_and_stale_resource(p3_lab):
    lab = p3_lab
    _, first = pending(lab)
    with write_transaction(lab.gateway.engine) as c:
        c.execute(
            update(principals)
            .where(principals.c.id == "p3-operator")
            .values(disabled=True)
        )
    with pytest.raises(ApiError) as e:
        lab.approvals.resolve(
            first.approval_id, lab.principal("approver"), "approve", 1, "Revocada"
        )
    assert e.value.status_code == 403
    with write_transaction(lab.gateway.engine) as c:
        c.execute(
            update(principals)
            .where(principals.c.id == "p3-operator")
            .values(disabled=False)
        )
    _, second = pending(lab)
    with write_transaction(lab.runtime.active().engine) as c:
        c.execute(
            text(
                "UPDATE resource_versions SET version=version+1 WHERE resource_id='mailbox:demo-outbox'"
            )
        )
    with pytest.raises(ApiError) as e:
        lab.approvals.resolve(
            second.approval_id,
            lab.principal("approver"),
            "approve",
            1,
            "Recurso cambiado",
        )
    assert e.value.code == "STALE_RESOURCE"


def test_audit_failure_rolls_back_before_effect(p3_lab):
    lab = p3_lab

    class Broken:
        def append(self, *_):
            raise RuntimeError("failure")

    lab.gateway.audit = Broken()
    with pytest.raises(ApiError) as e:
        lab.gateway.submit(lab.call("file.read"), lab.principal(), str(uuid4()))
    assert e.value.code == "AUDIT_UNAVAILABLE"
    with lab.gateway.engine.connect() as c:
        assert not c.execute(select(executions)).all()


def test_approval_audit_failure_cannot_consume(p3_lab):
    lab = p3_lab
    _, view = pending(lab)
    original = lab.gateway.audit

    class Broken:
        def append(self, *_):
            raise RuntimeError("failure")

    lab.gateway.audit = Broken()
    with pytest.raises(ApiError):
        lab.approvals.resolve(
            view.approval_id, lab.principal("approver"), "approve", 1, "Auditoría caída"
        )
    lab.gateway.audit = original
    assert (
        lab.approvals.get(view.approval_id, lab.principal("viewer"))["status"]
        == "PENDING"
    )
    assert lab.runtime.active().snapshot().outbox_count == 0


def test_timeout_after_effect_unknown_and_recovery_does_not_resend(p3_lab):
    lab = p3_lab
    original = lab.gateway.executor

    class Ambiguous:
        calls = 0

        def resource_version(self, resource):
            return original.resource_version(resource)

        def execute(self, call, capability):
            self.calls += 1
            original.execute(call, capability)
            raise TimeoutError()

        def receipt(self, execution_id):
            return original.receipt(execution_id)

    ambiguous = Ambiguous()
    lab.gateway.executor = ambiguous
    _, view = pending(lab)
    detail = lab.approvals.resolve(
        view.approval_id, lab.principal("approver"), "approve", 1, "Timeout controlado"
    )
    assert detail["request_state"] == "UNKNOWN"
    lab.gateway.recover()
    assert lab.gateway.get(view.request_id, lab.principal()).state == "SUCCEEDED"
    assert ambiguous.calls == 1 and lab.runtime.active().snapshot().outbox_count == 1


def test_receipt_mismatch_remains_unknown(p3_lab):
    lab = p3_lab
    original = lab.gateway.executor

    class Mismatch:
        def resource_version(self, resource):
            return original.resource_version(resource)

        def execute(self, call, capability):
            return original.execute(call, capability).model_copy(
                update={"request_id": str(uuid4())}
            )

        def receipt(self, execution_id):
            return None

    lab.gateway.executor = Mismatch()
    view = lab.gateway.submit(lab.call("file.read"), lab.principal(), str(uuid4()))
    assert view.state == "UNKNOWN"
    lab.gateway.recover()
    assert lab.gateway.get(view.request_id, lab.principal()).state == "UNKNOWN"


def test_http_auth_scopes_validation_and_approval(p3_lab):
    lab = p3_lab
    call = lab.call()
    assert (
        lab.client.post(
            "/api/v1/tool-requests", json=call.model_dump(mode="json")
        ).status_code
        == 401
    )
    headers = lab.login()
    assert (
        lab.client.post(
            "/api/v1/tool-requests", json=call.model_dump(mode="json"), headers=headers
        ).status_code
        == 422
    )
    response = lab.client.post(
        "/api/v1/tool-requests",
        json=call.model_dump(mode="json"),
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202, response.text
    apid = response.json()["approval_id"]
    assert (
        lab.client.post(
            f"/api/v1/approvals/{apid}/approve",
            json={"expected_version": 1, "reason": "x"},
            headers=headers,
        ).status_code
        == 403
    )
    approver = lab.login("approver")
    assert (
        lab.client.post(
            f"/api/v1/approvals/{apid}/approve",
            json={"expected_version": 1, "reason": "x", "parameters": {}},
            headers=approver,
        ).status_code
        == 422
    )
    detail = lab.client.post(
        f"/api/v1/approvals/{apid}/approve",
        json={"expected_version": 1, "reason": "Revisado"},
        headers=approver,
    )
    assert detail.status_code == 200 and detail.json()["status"] == "CONSUMED", (
        detail.text
    )
    replay = lab.client.post(
        f"/api/v1/approvals/{apid}/approve",
        json={"expected_version": 1, "reason": "Replay"},
        headers=approver,
    )
    assert replay.status_code == 409
    assert lab.runtime.active().snapshot().outbox_count == 1


def test_agent_exact_scope_identity_and_no_approvals(p3_lab):
    lab = p3_lab
    raw = "synthetic-agent-bearer-test"
    lab.app.state.person3_auth.repository.add_agent_credential(
        AgentCredentialRecord(
            hash_opaque_token(raw),
            "demo-agent",
            "p3-agent",
            frozenset({Scope("file.read", "file:public-guide")}),
            None,
        )
    )
    headers = {"Authorization": f"Bearer {raw}", "Idempotency-Key": str(uuid4())}
    response = lab.client.post(
        "/api/v1/tool-requests",
        json=lab.call("file.read").model_dump(mode="json"),
        headers=headers,
    )
    assert response.status_code == 200 and response.json()["state"] == "SUCCEEDED", (
        response.text
    )
    assert (
        lab.client.post(
            "/api/v1/tool-requests",
            json=lab.call("record.delete").model_dump(mode="json"),
            headers=headers,
        ).status_code
        == 403
    )
    assert lab.client.get("/api/v1/approvals", headers=headers).status_code == 403


def test_policy_admin_real_router_requires_csrf(p3_lab):
    lab = p3_lab
    body = {"format": "json", "content": json.dumps(lab.policy_data)}
    viewer = lab.login("viewer")
    assert (
        lab.client.post(
            "/api/v1/policies/validate", json=body, headers=viewer
        ).status_code
        == 403
    )
    admin = lab.login("admin")
    assert (
        lab.client.post(
            "/api/v1/policies/validate", json=body, headers={"Origin": ORIGIN}
        ).status_code
        == 403
    )
    assert (
        lab.client.post(
            "/api/v1/policies/validate", json=body, headers=admin
        ).status_code
        == 200
    )


def test_list_filters_pagination_and_unknown(p3_lab):
    lab = p3_lab
    for _ in range(3):
        pending(lab)
    first = lab.approvals.list(lab.principal("viewer"), limit=2)
    second = lab.approvals.list(
        lab.principal("viewer"), limit=2, cursor=first["next_cursor"]
    )
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert not {a["approval_id"] for a in first["items"]}.intersection(
        {a["approval_id"] for a in second["items"]}
    )
    assert lab.approvals.list(lab.principal("viewer"), status="REJECTED")["items"] == []
    with pytest.raises(ApiError):
        lab.approvals.list(lab.principal("viewer"), cursor="garbage")


@pytest.mark.parametrize("scenario", ["S06", "S07", "S10"])
def test_real_paired_demo_with_human_and_evidence(p3_lab, scenario):
    lab = p3_lab
    operator = lab.login()
    response = lab.client.post(
        "/api/v1/demo-runs",
        json={"scenario_id": scenario, "seed": 0, "mode": "paired"},
        headers=operator,
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    listing = lab.client.get("/api/v1/approvals").json()
    assert len(listing["items"]) == 1, listing
    ap = listing["items"][0]
    approver = lab.login("approver")
    response = lab.client.post(
        f"/api/v1/approvals/{ap['approval_id']}/approve",
        json={"expected_version": 1, "reason": "Demostración con revisión humana"},
        headers=approver,
    )
    assert (
        response.status_code == 200 and response.json()["request_state"] == "SUCCEEDED"
    ), response.text
    run = lab.client.get(f"/api/v1/demo-runs/{run_id}")
    assert run.status_code == 200 and run.json()["status"] == "COMPLETED", run.text
    evidence = lab.client.get(f"/api/v1/demo-runs/{run_id}/evidence")
    assert evidence.status_code == 200
    assert lab.runtime.active().snapshot().outbox_count == 1
