"""Activa policies/demo.yaml solo si el perfil demo no tiene política activa."""

from __future__ import annotations

from pathlib import Path

from wallba.auth.clock import SystemClock
from wallba.policy.loader import load_policy
from wallba.policy.repository import SqlitePolicyRepository
from wallba.policy.schemas import canonical_bytes
from wallba.policy.service import PolicyConflict, PolicyService


def demo_policy_path() -> Path | None:
    candidates = (
        Path("/app/policies/demo.yaml"),
        Path(__file__).resolve().parents[3] / "policies" / "demo.yaml",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def ensure_demo_policy(db_path: Path, audit, enabled: bool) -> bool:
    if not enabled:
        return False
    repository = SqlitePolicyRepository(db_path)
    if repository.get_active_snapshot() is not None:
        return False
    path = demo_policy_path()
    if path is None:
        return False
    report = load_policy(path.read_bytes(), "yaml")
    if not report.valid or report.document is None:
        return False
    service = PolicyService(repository, SystemClock(), audit)
    try:
        service.create_version("demo-policy", canonical_bytes(report.document), "demo-policy-admin")
    except PolicyConflict:
        pass
    service.activate("demo-policy", 1, None, "demo-policy-admin")
    return True
