"""Genera contracts/openapi.json y los vectores canónicos desde los DTO Python.

Uso (desde la raíz): uv run --project backend python scripts/export_contracts.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic import TypeAdapter  # noqa: E402

from wallba.contracts.api import ErrorResponse  # noqa: E402
from wallba.contracts.canonical import CanonicalRequest  # noqa: E402
from wallba.contracts.capability import Capability, capability_signing_bytes, compute_signature  # noqa: E402
from wallba.contracts.decision import DecisionEnvelope, ExecutionReceipt, RequestView  # noqa: E402
from wallba.contracts.results import ToolResult  # noqa: E402
from wallba.contracts.tool_call import ToolCall  # noqa: E402
from wallba.foundation.app import create_app  # noqa: E402
from wallba.foundation.config import Settings  # noqa: E402
from wallba.foundation.http import Integrations  # noqa: E402
from wallba.observability.router import router as observability_router  # noqa: E402

SHARED_DTOS: dict[str, Any] = {
    "ToolCall": ToolCall,
    "ToolResult": ToolResult,
    "DecisionEnvelope": DecisionEnvelope,
    "ExecutionReceipt": ExecutionReceipt,
    "RequestView": RequestView,
    "ErrorResponse": ErrorResponse,
}
VECTOR_SECRET = "test-only-capability-secret-not-for-production"


def build_openapi() -> dict[str, Any]:
    settings = Settings(
        role="control",
        environment_id="protected-fixture",
        executor_url="http://executor",
        executor_token="placeholder",
    )
    document = create_app(settings, Integrations(extra_routers=[observability_router])).openapi()
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    for name, dto in SHARED_DTOS.items():
        schema = TypeAdapter(dto).json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(schema.pop("$defs", {}))
        schemas.setdefault(name, schema)
    # Orden estable: el diff de CI solo refleja cambios reales.
    return json.loads(json.dumps(document, sort_keys=True))


def build_vectors() -> dict[str, Any]:
    request = CanonicalRequest.model_validate(
        {
            "call": {
                "request_id": "22222222-2222-4222-8222-222222222222",
                "agent_id": "demo-agent",
                "tool": "email.send",
                "operation": "send",
                "resource_id": "mailbox:demo-outbox",
                "parameters": {
                    "to": "reviewer@example.test",
                    "subject": "Revisión ñandú",
                    "body": "Contenido sintético.",
                },
            },
            "principal_id": "demo-operator",
            "environment_id": "protected-fixture",
            "resource_version": 1,
        }
    )
    unsigned = Capability(
        execution_id="33333333-3333-4333-8333-333333333333",
        request_digest=request.digest(),
        principal_id=request.principal_id,
        environment_id=request.environment_id,
        resource_version=request.resource_version,
        policy_id="demo-policy",
        policy_version=1,
        expires_at="2026-10-31T12:00:30Z",
        nonce="0123456789abcdef0123456789abcdef",
        key_id="test-key",
        signature="0" * 64,
    )
    signing = capability_signing_bytes(unsigned)
    signed = unsigned.model_copy(update={"signature": compute_signature(signing, VECTOR_SECRET.encode())})
    return {
        "note": "Vectores para verificar canonicalización y HMAC entre P1 y P3. Secreto solo de prueba.",
        "test_secret": VECTOR_SECRET,
        "canonical_request": request.model_dump(mode="json"),
        "canonical_bytes": request.canonical_bytes().decode("utf-8"),
        "request_digest": request.digest(),
        "capability": signed.model_dump(mode="json"),
        "capability_signing_bytes": signing.decode("utf-8"),
    }


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> None:
    _write(ROOT / "contracts" / "openapi.json", build_openapi())
    _write(ROOT / "contracts" / "examples" / "canonical_vectors.json", build_vectors())


if __name__ == "__main__":
    main()
