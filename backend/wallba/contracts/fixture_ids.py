"""Identificadores deterministas de fixtures, sin datos ni rutas."""

from __future__ import annotations

import uuid

FIXTURE_VERSION = "2026-10-31.1"
RECORD_COUNT = 8
_NAMESPACE = uuid.UUID("6f1f0c52-7b1e-5d7a-9a43-3f6f2e1c9a10")


def record_id(seed: int, index: int) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"record:{FIXTURE_VERSION}:{seed}:{index}"))


def target_record_id(seed: int) -> str:
    """Fila que los escenarios destructivos intentan borrar."""
    return record_id(seed, 0)


def request_id(run_id: str, scenario_id: str, step: int) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"request:{run_id}:{scenario_id}:{step}"))
