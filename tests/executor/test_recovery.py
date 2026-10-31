"""Reinicios y fallos: nunca repetir un efecto a ciegas (WAL-P1-006, WAL-P1-010)."""

from __future__ import annotations

from pathlib import Path

import pytest
from support.fakes import CAPABILITY_SECRET, ENVIRONMENT_ID, KEY_ID, sign_capability

from wallba.contracts.canonical import CanonicalRequest
from wallba.contracts.fixture_ids import target_record_id
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER
from wallba.executor.capabilities import CapabilityVerifier
from wallba.executor.runtime import DEFAULT_SEED, ExecutorRuntime
from wallba.executor.sandbox import SandboxError
from wallba.executor.service import ExecutorService


class SimulatedCrash(Exception):
    pass


def _crash_at(point: str):
    def hook(current: str) -> None:
        if current == point:
            raise SimulatedCrash(point)

    return hook


def _service(runtime: ExecutorRuntime, fault=None) -> ExecutorService:
    verifier = CapabilityVerifier({KEY_ID: CAPABILITY_SECRET}, ENVIRONMENT_ID)
    kwargs = {"fault": fault} if fault else {}
    return ExecutorService(runtime, verifier, **kwargs)


def _request() -> CanonicalRequest:
    call = TOOL_CALL_ADAPTER.validate_python(
        {
            "request_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "agent_id": "demo-agent",
            "tool": "record.delete",
            "operation": "delete",
            "resource_id": "table:demo-records",
            "parameters": {"record_id": target_record_id(DEFAULT_SEED)},
        }
    )
    return CanonicalRequest(
        call=call, principal_id="demo-operator", environment_id=ENVIRONMENT_ID, resource_version=1
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "sandboxes"


def test_crash_before_commit_rolls_back_effect_and_journal(root: Path) -> None:
    runtime = ExecutorRuntime(root, "executor")
    request = _request()
    capability = sign_capability(request)
    with pytest.raises(SimulatedCrash):
        _service(runtime, _crash_at("before_commit")).execute(request, capability)
    snapshot = runtime.active().snapshot()
    assert snapshot.record_count == 8
    assert snapshot.journal_count == 0
    assert _service(runtime).receipt(capability.execution_id) is None
    runtime.sandboxes.dispose()


def test_crash_after_commit_keeps_receipt_and_retry_does_not_repeat(root: Path) -> None:
    runtime = ExecutorRuntime(root, "executor")
    request = _request()
    capability = sign_capability(request)
    with pytest.raises(SimulatedCrash):
        _service(runtime, _crash_at("after_commit")).execute(request, capability)
    runtime.sandboxes.dispose()

    # Nuevo proceso sobre el mismo volumen: el resultado se recupera por execution_id.
    restarted = ExecutorRuntime(root, "executor")
    service = _service(restarted)
    recovered = service.receipt(capability.execution_id)
    assert recovered is not None
    assert recovered.state == "SUCCEEDED"
    assert recovered.effect_count == 1

    again = service.execute(request, capability)
    assert again == recovered
    snapshot = restarted.active().snapshot()
    assert snapshot.record_count == 7
    assert snapshot.journal_count == 1
    restarted.sandboxes.dispose()


def test_tool_failure_produces_failed_receipt_with_no_effect(root: Path) -> None:
    runtime = ExecutorRuntime(root, "executor")
    target = runtime.active().files_dir / "public-guide.txt"
    target.chmod(0o666)
    target.unlink()
    call = TOOL_CALL_ADAPTER.validate_python(
        {
            "request_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "agent_id": "demo-agent",
            "tool": "file.read",
            "operation": "read",
            "resource_id": "file:public-guide",
            "parameters": {"max_bytes": 10},
        }
    )
    request = CanonicalRequest(
        call=call, principal_id="demo-operator", environment_id=ENVIRONMENT_ID, resource_version=1
    )
    receipt = _service(runtime).execute(request, sign_capability(request))
    assert receipt.state == "FAILED"
    assert receipt.effect_count == 0
    assert receipt.result_digest is None
    runtime.sandboxes.dispose()


def test_active_environment_survives_restart(root: Path) -> None:
    runtime = ExecutorRuntime(root, "executor")
    run_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    runtime.activate(run_id, 3)
    runtime.sandboxes.dispose()
    restarted = ExecutorRuntime(root, "executor")
    assert restarted.active().run_id == run_id
    restarted.sandboxes.dispose()


def test_nonce_cannot_be_replayed_in_a_later_run(root: Path) -> None:
    runtime = ExecutorRuntime(root, "executor")
    request = _request()
    nonce = "cd" * 16
    service = _service(runtime)
    service.execute(request, sign_capability(request, nonce=nonce))
    runtime.activate("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", DEFAULT_SEED)
    from wallba.executor.errors import CapabilityRejected

    with pytest.raises(CapabilityRejected) as error:
        service.execute(request, sign_capability(request, nonce=nonce))
    assert error.value.code == "NONCE_REPLAY"
    assert runtime.active().snapshot().record_count == 8
    runtime.sandboxes.dispose()


def test_reset_rejects_active_environment(root: Path) -> None:
    runtime = ExecutorRuntime(root, "executor")
    active = runtime.active().run_id
    with pytest.raises(SandboxError):
        runtime.reset(active)
    assert runtime.active().snapshot().record_count == 8
    runtime.sandboxes.dispose()
