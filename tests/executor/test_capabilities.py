"""El ejecutor rechaza capacidades inválidas con cero efecto (WAL-P1-006)."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from conftest import executor_settings
from fastapi.testclient import TestClient
from support.fakes import CAPABILITY_SECRET, ENVIRONMENT_ID, EXECUTOR_TOKEN, KEY_ID, sign_capability

from wallba.contracts.canonical import CanonicalRequest
from wallba.contracts.capability import compute_signature, capability_signing_bytes
from wallba.contracts.fixture_ids import target_record_id
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER
from wallba.executor.app import create_executor_app
from wallba.executor.errors import CapabilityRejected
from wallba.executor.runtime import DEFAULT_SEED

REQUEST_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _delete_request(resource_version: int = 1) -> CanonicalRequest:
    call = TOOL_CALL_ADAPTER.validate_python(
        {
            "request_id": REQUEST_ID,
            "agent_id": "demo-agent",
            "tool": "record.delete",
            "operation": "delete",
            "resource_id": "table:demo-records",
            "parameters": {"record_id": target_record_id(DEFAULT_SEED)},
        }
    )
    return CanonicalRequest(
        call=call,
        principal_id="demo-operator",
        environment_id=ENVIRONMENT_ID,
        resource_version=resource_version,
    )


def _records(runtime) -> int:
    return runtime.active().snapshot().record_count


def _journal(runtime) -> int:
    return runtime.active().snapshot().journal_count


def test_valid_capability_executes_once(service, runtime) -> None:
    request = _delete_request()
    receipt = service.execute(request, sign_capability(request))
    assert receipt.state == "SUCCEEDED"
    assert receipt.effect_count == 1
    assert _records(runtime) == 7


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"secret": b"z" * 32}, "INVALID_SIGNATURE"),
        ({"key_id": "otra-clave"}, "UNKNOWN_KEY"),
        ({"expires_in": -10}, "CAPABILITY_EXPIRED"),
        ({"expires_in": 3600}, "CAPABILITY_TTL_TOO_LONG"),
        ({"environment_id": "baseline-fixture"}, "ENVIRONMENT_MISMATCH"),
        ({"principal_id": "demo-approver"}, "PRINCIPAL_MISMATCH"),
        ({"request_digest": "a" * 64}, "DIGEST_MISMATCH"),
        ({"resource_version": 99}, "STALE_RESOURCE"),
    ],
)
def test_invalid_capability_has_zero_effect(service, runtime, overrides: dict, code: str) -> None:
    request = _delete_request()
    with pytest.raises(CapabilityRejected) as error:
        service.execute(request, sign_capability(request, **overrides))
    assert error.value.code == code
    assert _records(runtime) == 8
    assert _journal(runtime) == 0


def test_tampered_field_breaks_signature(service, runtime) -> None:
    request = _delete_request()
    capability = sign_capability(request).model_copy(update={"policy_version": 2})
    with pytest.raises(CapabilityRejected) as error:
        service.execute(request, capability)
    assert error.value.code == "INVALID_SIGNATURE"
    assert _journal(runtime) == 0


def test_altered_request_body_is_digest_mismatch(service, runtime) -> None:
    request = _delete_request()
    capability = sign_capability(request)
    other_call = TOOL_CALL_ADAPTER.validate_python(
        {
            **request.call.model_dump(mode="json"),
            "parameters": {"record_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd"},
        }
    )
    with pytest.raises(CapabilityRejected) as error:
        service.execute(request.model_copy(update={"call": other_call}), capability)
    assert error.value.code == "DIGEST_MISMATCH"
    assert _records(runtime) == 8


def test_stale_resource_version_is_checked_against_the_store(service, runtime) -> None:
    # Capacidad bien firmada, pero con una versión de recurso superada.
    request = _delete_request(resource_version=5)
    with pytest.raises(CapabilityRejected) as error:
        service.execute(request, sign_capability(request))
    assert error.value.code == "STALE_RESOURCE"
    assert _records(runtime) == 8


def test_same_execution_replay_returns_same_receipt_without_new_effect(service, runtime) -> None:
    request = _delete_request()
    capability = sign_capability(request)
    first = service.execute(request, capability)
    second = service.execute(request, capability)
    assert first == second
    assert _journal(runtime) == 1


def test_reused_nonce_with_new_execution_is_rejected(service, runtime) -> None:
    request = _delete_request()
    nonce = "ab" * 16
    service.execute(request, sign_capability(request, nonce=nonce))
    fresh = _delete_request(resource_version=2)
    with pytest.raises(CapabilityRejected) as error:
        service.execute(fresh, sign_capability(fresh, nonce=nonce))
    assert error.value.code == "NONCE_REPLAY"
    assert _journal(runtime) == 1


def test_execution_id_with_other_payload_gets_no_foreign_receipt(service, runtime) -> None:
    request = _delete_request()
    capability = sign_capability(request)
    service.execute(request, capability)
    other = _delete_request(resource_version=2)
    with pytest.raises(CapabilityRejected) as error:
        service.execute(other, sign_capability(other, execution_id=capability.execution_id))
    assert error.value.code == "NONCE_REPLAY"


def test_expiry_uses_clock_tolerance(runtime) -> None:
    from wallba.executor.capabilities import CapabilityVerifier

    now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    request = _delete_request()
    capability = sign_capability(request, now=now, expires_in=0)
    within = CapabilityVerifier({KEY_ID: CAPABILITY_SECRET}, ENVIRONMENT_ID, lambda: now + timedelta(seconds=2))
    within.verify(request, capability)
    beyond = CapabilityVerifier({KEY_ID: CAPABILITY_SECRET}, ENVIRONMENT_ID, lambda: now + timedelta(seconds=3))
    with pytest.raises(CapabilityRejected):
        beyond.verify(request, capability)


def test_concurrent_calls_produce_a_single_effect(service, runtime) -> None:
    request = _delete_request()
    capability = sign_capability(request)
    runtime.active()
    barrier = threading.Barrier(4)
    receipts = []

    def worker() -> None:
        barrier.wait()
        receipts.append(service.execute(request, capability))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(receipts) == 4
    assert len({receipt.execution_id for receipt in receipts}) == 1
    assert _records(runtime) == 7
    assert _journal(runtime) == 1


class TestInternalHttp:
    @pytest.fixture
    def client(self, tmp_path, runtime):
        with TestClient(create_executor_app(executor_settings(tmp_path), runtime)) as value:
            yield value

    AUTH = {"Authorization": f"Bearer {EXECUTOR_TOKEN}"}

    def _body(self, request, capability) -> dict:
        return {"request": request.model_dump(mode="json"), "capability": capability.model_dump(mode="json")}

    def test_call_without_service_token_is_rejected(self, client, runtime) -> None:
        request = _delete_request()
        response = client.post("/internal/execute", json=self._body(request, sign_capability(request)))
        assert response.status_code == 401
        assert _journal(runtime) == 0

    def test_direct_call_without_capability_is_rejected(self, client, runtime) -> None:
        request = _delete_request()
        response = client.post(
            "/internal/execute", json={"request": request.model_dump(mode="json")}, headers=self.AUTH
        )
        assert response.status_code == 422
        assert _journal(runtime) == 0

    def test_protected_process_has_no_unsafe_route(self, client) -> None:
        call = _delete_request().call.model_dump(mode="json")
        response = client.post("/internal/baseline/execute", json=call, headers=self.AUTH)
        assert response.status_code == 404

    def test_rejection_status_codes(self, client) -> None:
        request = _delete_request()
        bad = client.post(
            "/internal/execute",
            json=self._body(request, sign_capability(request, secret=b"z" * 32)),
            headers=self.AUTH,
        )
        assert bad.status_code == 403
        assert bad.json()["detail"] == "INVALID_SIGNATURE"

    def test_receipt_endpoint_recovers_result(self, client) -> None:
        request = _delete_request()
        capability = sign_capability(request)
        assert client.post("/internal/execute", json=self._body(request, capability), headers=self.AUTH).status_code == 200
        receipt = client.get(f"/internal/receipts/{capability.execution_id}", headers=self.AUTH)
        assert receipt.json()["effect_count"] == 1
        result = client.get(f"/internal/results/{capability.execution_id}", headers=self.AUTH)
        assert result.json()["deleted_count"] == 1
        assert client.get(f"/internal/receipts/{'e' * 8}-eeee-4eee-8eee-{'e' * 12}", headers=self.AUTH).status_code == 404

    def test_signature_helper_matches_contract(self) -> None:
        request = _delete_request()
        capability = sign_capability(request)
        assert compute_signature(capability_signing_bytes(capability), CAPABILITY_SECRET) == capability.signature
