"""Agente de prueba. Aplica la decisión antes de tocar el archivo."""

from __future__ import annotations

from pathlib import Path

from wallba.guard.policy import decide


def attempt(root: Path, target: Path, decision_posture: str | None, operation: str, *, apply: bool, content: bytes | None) -> dict:
    before = target.read_bytes() if target.is_file() and not target.is_symlink() else None
    decision = decide(decision_posture, operation)
    changed = False
    if decision.effect == "DENY":
        after = target.read_bytes() if target.is_file() and not target.is_symlink() else None
        return {
            "effect": decision.effect,
            "preventive": decision.preventive,
            "covered": decision.covered,
            "reason": decision.reason,
            "changed": False,
            "intact": before == after,
            "outcome": "blocked",
            "origin_detail": "wallba-test-agent",
        }
    if apply and operation == "write":
        if target.is_symlink() or not target.is_file():
            raise OSError("el shim solo escribe archivos regulares")
        target.write_bytes(content if content is not None else b"wallba-probe\n")
        changed = True
    if apply and operation == "delete":
        if target.is_symlink() or not target.is_file():
            raise OSError("el shim solo elimina archivos regulares")
        target.unlink()
        changed = True
    outcome = "observed" if decision.covered else "allowed_unprotected"
    return {
        "effect": decision.effect,
        "preventive": False,
        "covered": decision.covered,
        "reason": decision.reason,
        "changed": changed,
        "intact": not changed,
        "outcome": outcome,
        "origin_detail": "wallba-test-agent",
        "root": str(root),
    }
