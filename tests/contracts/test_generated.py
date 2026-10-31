"""El snapshot de OpenAPI publicado coincide con el código (WAL-P1-001)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _export_module():
    spec = importlib.util.spec_from_file_location("export_contracts", ROOT / "scripts" / "export_contracts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openapi_snapshot_is_current() -> None:
    published = json.loads((ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8"))
    assert published == _export_module().build_openapi()


def test_snapshot_exposes_shared_dtos_and_no_internal_routes() -> None:
    published = json.loads((ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8"))
    for name in ("FileReadCall", "DecisionEnvelope", "ExecutionReceipt", "RequestView", "ErrorResponse"):
        assert name in published["components"]["schemas"]
    assert not [path for path in published["paths"] if path.startswith("/internal")]


def test_generated_client_is_marked_and_present() -> None:
    generated = (ROOT / "frontend" / "src" / "api" / "generated.ts").read_text(encoding="utf-8")
    assert "components" in generated and "ExecutionReceipt" in generated
