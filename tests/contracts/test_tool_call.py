"""Pruebas de contrato para ToolCall, decisiones y recibos (WAL-P1-001)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from wallba.contracts.decision import DecisionEnvelope, ExecutionReceipt
from wallba.contracts.tool_call import ToolCall

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"
ADAPTER: TypeAdapter[Any] = TypeAdapter(ToolCall)


def _load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _base(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "request_id": "55555555-5555-4555-8555-555555555555",
        "agent_id": "demo-agent",
        "tool": "file.read",
        "operation": "read",
        "resource_id": "file:public-guide",
        "parameters": {"max_bytes": 1024},
    }
    data.update(overrides)
    return data


def test_example_allow_is_valid() -> None:
    call = ADAPTER.validate_python(_load("tool_call_file_read_allow.json"))
    assert call.tool == "file.read"


def test_example_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_load("tool_call_invalid_extra_field.json"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"operation": "send"},  # operation incoherente con file.read
        {"resource_id": "table:demo-records"},  # recurso de otra herramienta
        {"parameters": {"max_bytes": 16385}},  # fuera de rango
        {"parameters": {"max_bytes": True}},  # bool no es entero en modo estricto
        {"parameters": {"max_bytes": 10, "path": "/etc/passwd"}},  # clave extra
        {"agent_id": ""},  # identificador vacío
        {"tool": "shell.exec"},  # herramienta fuera del catálogo
    ],
)
def test_incoherent_or_unknown_file_read_is_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_base(**overrides))


def test_authority_fields_are_not_accepted_from_client() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_base(roles=["admin"]))
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(_base(environment_id="protected-fixture"))


def test_email_only_accepts_test_domain() -> None:
    payload = {
        "request_id": "66666666-6666-4666-8666-666666666666",
        "agent_id": "demo-agent",
        "tool": "email.send",
        "operation": "send",
        "resource_id": "mailbox:demo-outbox",
        "parameters": {"to": "cliente@empresa.com", "subject": "Hola", "body": "x"},
    }
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(payload)
    payload["parameters"]["to"] = "cliente@demo.test"
    assert ADAPTER.validate_python(payload).tool == "email.send"


def test_db_query_accepts_only_predefined_query_ids() -> None:
    payload = {
        "request_id": "77777777-7777-4777-8777-777777777777",
        "agent_id": "demo-agent",
        "tool": "db.query",
        "operation": "query",
        "resource_id": "query:demo-records",
        "parameters": {"query_id": "DROP TABLE demo_records", "limit": 5},
    }
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(payload)


def test_decision_envelope_example_is_valid() -> None:
    envelope = DecisionEnvelope.model_validate(_load("decision_require_approval.json"))
    assert envelope.decision == "REQUIRE_APPROVAL"


def test_unknown_receipt_allows_null_effect_count() -> None:
    receipt = ExecutionReceipt.model_validate(
        {
            "execution_id": "exec-1",
            "request_id": "req-1",
            "state": "UNKNOWN",
            "result_digest": None,
            "effect_count": None,
            "evidence_id": "ev-1",
            "completed_at": None,
        }
    )
    assert receipt.effect_count is None


def test_receipt_rejects_unknown_state() -> None:
    with pytest.raises(ValidationError):
        ExecutionReceipt.model_validate(
            {
                "execution_id": "exec-1",
                "request_id": "req-1",
                "state": "PENDING",
                "result_digest": None,
                "effect_count": 0,
                "evidence_id": "ev-1",
                "completed_at": None,
            }
        )
