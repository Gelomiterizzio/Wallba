"""Manifest versionado: hechos observados, separados de las expectativas."""

from __future__ import annotations

import os
import platform
from datetime import datetime
from importlib import metadata
from typing import Any

from wallba.contracts.api import SideView
from wallba.contracts.canonical import canonical_json, sha256_hex
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER, ToolCall
from wallba.demo.scenarios import SCENARIO_VERSION, Scenario

MANIFEST_SCHEMA_VERSION = "1"
_RUNTIME_PACKAGES = ("fastapi", "pydantic", "sqlalchemy")


def _runtime_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for package in _RUNTIME_PACKAGES:
        versions[package] = metadata.version(package)
    return versions


def _redact_call(call: ToolCall) -> dict[str, Any]:
    """El cuerpo del correo sale como digest; el resto de la llamada es fixture."""
    data = TOOL_CALL_ADAPTER.dump_python(call, mode="json")
    if call.tool == "email.send":
        body = data["parameters"].pop("body")
        data["parameters"]["body_digest"] = sha256_hex(body.encode("utf-8"))
    return data


def _call_digest(call: ToolCall) -> str:
    return sha256_hex(canonical_json(TOOL_CALL_ADAPTER.dump_python(call, mode="json")))


def _side_assertions(side: SideView) -> dict[str, Any]:
    """Compara antes/después. Sin ambas observaciones no se afirma nada (null)."""
    if side.before is None or side.after is None:
        return {
            "state_changed": None,
            "records_removed": None,
            "outbox_added": None,
            "journal_added": None,
        }
    return {
        "state_changed": side.before.state_digest != side.after.state_digest,
        "records_removed": side.before.record_count - side.after.record_count,
        "outbox_added": side.after.outbox_count - side.before.outbox_count,
        "journal_added": side.after.journal_count - side.before.journal_count,
    }


def side_effect_count(side: SideView) -> int | None:
    """Suma de receipts; un receipt sin conteo vuelve incierto el total."""
    counts = [receipt.effect_count for receipt in side.receipts]
    return None if any(count is None for count in counts) else sum(counts)


def _policy_binding(protected: SideView) -> dict[str, Any]:
    decision = protected.decisions[-1] if protected.decisions else None
    return {
        "policy_id": decision.policy_id if decision else None,
        "policy_version": decision.policy_version if decision else None,
        # El checksum lo publica P2; no se inventa mientras no venga en el contrato.
        "policy_checksum": None,
    }


def _side_manifest(side: SideView) -> dict[str, Any]:
    return side.model_dump(mode="json")


def build_manifest(
    *,
    evidence_id: str,
    run_id: str,
    scenario: Scenario,
    seed: int,
    fixture_digest: str | None,
    calls: list[ToolCall],
    transcript_digest: str | None,
    baseline: SideView,
    protected: SideView,
    audit_event_ids: list[str],
    notes: list[str],
    started_at: datetime,
    completed_at: datetime,
) -> tuple[dict[str, Any], str]:
    """Devuelve (manifest, manifest_digest)."""
    git_sha = os.environ.get("WALLBA_GIT_SHA") or None
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "run_id": run_id,
        "git_sha": git_sha,
        "git_sha_null_reason": None if git_sha else "WALLBA_GIT_SHA no configurado",
        "runtime_versions": _runtime_versions(),
        "scenario": {"id": scenario.id, "version": SCENARIO_VERSION},
        "seed": seed,
        "fixture_digest": fixture_digest,
        "calls": [{"call": _redact_call(call), "digest": _call_digest(call)} for call in calls],
        "transcript_digest": transcript_digest,
        "environments": {
            "baseline": baseline.environment_id,
            "protected": protected.environment_id,
        },
        "policy": _policy_binding(protected),
        "baseline": _side_manifest(baseline),
        "protected": _side_manifest(protected),
        "audit_event_ids": audit_event_ids,
        "observed_assertions": {
            "baseline": _side_assertions(baseline),
            "protected": _side_assertions(protected),
        },
        "notes": notes,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        # Bloque separado: una expectativa nunca se presenta como resultado.
        "expectations": {
            "label": "EXPECTATION",
            "baseline": scenario.expected_baseline,
            "protected": scenario.expected_protected,
        },
    }
    return manifest, sha256_hex(canonical_json(manifest))


def verify_manifest(manifest: dict[str, Any], digest: str) -> bool:
    return sha256_hex(canonical_json(manifest)) == digest
