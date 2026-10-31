"""Pruebas de contrato para ToolCall, decisiones y recibos (WAL-P1-001)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from wallba.contracts.decision import DecisionEnvelope, ExecutionReceipt, RequestView
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER as ADAPTER

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"
UUID_A = "55555555-5555-4555-8555-555555555555"
UUID_B = "66666666-6666-4666-8666-666666666666"
UUID_C = "77777777-7777-4777-8777-777777777777"


def _load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _base(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "request_id": UUID_A,
        "agent_id": "demo-agent",
        "tool": "file.read",
        "operation": "read",
        "resource_id": "file:public-guide",
        "parameters": {"max_bytes": 1024},
    }
    data.update(overrides)
    return data


def _email(**parameters: Any) -> dict[str, Any]:
    return {
        "request_id": UUID_B,
        "agent_id": "demo-agent",
        "tool": "email.send",
        "operation": "send",
        "resource_id": "mailbox:demo-outbox",
        "parameters": {"to": "cliente@demo.test", "subject": "Hola", "body": "x", **parameters},
    }


def test_example_allow_is_valid() -> None:
    assert ADAPTER.validate_python(_load("tool_call_file_read_allow.json")).tool == "file.read"


def test_example_deny_call_is_schema_valid() -> None:
    assert ADAPTER.validate_python(_load("tool_call_record_delete_deny.json")).tool == "record.delete"


def test_example_pending_call_is_schema_valid() -> None:
    assert ADAPTER.validate_python(_load("tool_call_email_pending.json")).tool == "email.send"


def test_example_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_load("tool_call_invalid_extra_field.json"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"operation": "send"},
        {"resource_id": "table:demo-records"},
        {"parameters": {"max_bytes": 16385}},
        {"parameters": {"max_bytes": 0}},
        {"parameters": {"max_bytes": True}},
        {"parameters": {"max_bytes": "10"}},
        {"parameters": {"max_bytes": 10, "path": "/etc/passwd"}},
        {"agent_id": ""},
        {"request_id": "no-es-uuid"},
        {"tool": "shell.exec"},
        {"resource_id": "../../.env"},
    ],
)
def test_incoherent_or_unknown_file_read_is_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_base(**overrides))


@pytest.mark.parametrize(
    "extra",
    [
        {"roles": ["admin"]},
        {"environment_id": "protected-fixture"},
        {"principal_id": "demo-approver"},
        {"risk": "LOW"},
    ],
)
def test_authority_fields_are_not_accepted_from_client(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_base(**extra))


def test_email_only_accepts_test_domain() -> None:
    assert ADAPTER.validate_python(_email()).tool == "email.send"
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_email(to="cliente@empresa.com"))


@pytest.mark.parametrize(
    "parameters",
    [
        {"subject": "x" * 121},
        {"body": "x" * 4097},
        {"body": "con byte nulo \x00"},
        {"subject": "control \x07"},
        {"body": "é sin normalizar"},
    ],
)
def test_email_text_limits_and_unsafe_characters_are_rejected(parameters: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_email(**parameters))


def test_db_query_accepts_only_predefined_query_ids() -> None:
    payload = {
        "request_id": UUID_C,
        "agent_id": "demo-agent",
        "tool": "db.query",
        "operation": "query",
        "resource_id": "query:demo-records",
        "parameters": {"query_id": "DROP TABLE demo_records", "limit": 5},
    }
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(payload)


def test_record_delete_requires_uuid() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(
            {
                "request_id": UUID_C,
                "agent_id": "demo-agent",
                "tool": "record.delete",
                "operation": "delete",
                "resource_id": "table:demo-records",
                "parameters": {"record_id": "1 OR 1=1"},
            }
        )


@pytest.mark.parametrize("name", ["decision_allow.json", "decision_deny.json", "decision_require_approval.json"])
def test_decision_examples_are_valid(name: str) -> None:
    assert DecisionEnvelope.model_validate(_load(name)).request_id


def test_unknown_receipt_allows_null_effect_count() -> None:
    receipt = ExecutionReceipt.model_validate_json(
        json.dumps(
            {
                "execution_id": UUID_A,
                "request_id": UUID_B,
                "state": "UNKNOWN",
                "result_digest": None,
                "effect_count": None,
                "evidence_id": UUID_C,
                "completed_at": None,
            }
        )
    )
    assert receipt.effect_count is None


def test_receipt_rejects_unknown_state_and_non_utc_timestamp() -> None:
    base = {
        "execution_id": UUID_A,
        "request_id": UUID_B,
        "state": "SUCCEEDED",
        "result_digest": None,
        "effect_count": 0,
        "evidence_id": UUID_C,
        "completed_at": "2026-10-31T12:00:00Z",
    }
    assert ExecutionReceipt.model_validate_json(json.dumps(base)).state == "SUCCEEDED"
    with pytest.raises(ValidationError):
        ExecutionReceipt.model_validate_json(json.dumps({**base, "state": "PENDING"}))
    with pytest.raises(ValidationError):
        ExecutionReceipt.model_validate_json(json.dumps({**base, "completed_at": "2026-10-31T12:00:00-04:00"}))


def test_request_view_example_is_valid() -> None:
    view = RequestView.model_validate_json((EXAMPLES / "request_view_pending.json").read_text(encoding="utf-8"))
    assert view.state == "PENDING_APPROVAL"


@pytest.mark.parametrize("name", ["401", "403", "409", "422", "503"])
def test_error_examples_follow_common_format(name: str) -> None:
    body = _load(f"error_{name}.json")
    assert set(body["error"]) == {"code", "message", "request_id", "details"}
