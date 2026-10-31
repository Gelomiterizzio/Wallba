"""Observación posterior. No identifica al proceso ni demuestra una lectura."""

from __future__ import annotations

from pathlib import Path

from wallba.guard.hook import UNDETERMINED
from wallba.guard.scanner import Scan, scan_tree

UNDETERMINED_EXPLANATION = (
    "El monitor vio un cambio de metadatos o la ausencia del archivo. "
    "No identifica al proceso y no demuestra una lectura. ORIGEN NO DETERMINADO."
)


def confirmed_missing(path: str, seen: set[str], listed: frozenset[str]) -> bool:
    if path in seen:
        return False
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    if parent in listed or (parent == "" and "" in listed):
        return True
    if parent and confirmed_missing(parent, seen, listed):
        return True
    return False


def diff(previous: dict[str, tuple], scanned: Scan, covered) -> list[dict]:
    """covered(path) -> posture or None. No restaura archivos."""
    seen = {item.relative_path: item for item in scanned.entries}
    events: list[dict] = []
    for item in scanned.entries:
        stamp = (item.mtime_ns, item.size_bytes, item.kind)
        old = previous.get(item.relative_path)
        if item.kind != "file":
            continue
        if old is None:
            posture = covered(item.relative_path)
            if posture is None and item.classification.risk not in {"CRITICAL", "HIGH"}:
                continue
            events.append(
                {
                    "relative_path": item.relative_path,
                    "operation": "create",
                    "outcome": "detected",
                    "origin_detail": UNDETERMINED,
                    "preventive": False,
                    "severity": "high",
                    "explanation": UNDETERMINED_EXPLANATION,
                    "action_taken": "Se registró un archivo nuevo. No se bloqueó ni se leyó su contenido.",
                }
            )
            continue
        if old == stamp:
            continue
        posture = covered(item.relative_path)
        if posture is None:
            continue
        events.append(
            {
                "relative_path": item.relative_path,
                "operation": "modify",
                "outcome": "detected",
                "origin_detail": UNDETERMINED,
                "preventive": False,
                "severity": "high" if posture in {"alert", "block_read", "block_write", "block_all"} else "medium",
                "explanation": UNDETERMINED_EXPLANATION,
                "action_taken": "Se registró el cambio después de ocurrir. No se restauró el archivo.",
            }
        )
    for path, old in previous.items():
        if path in seen or old[2] != "file":
            continue
        if not confirmed_missing(path, set(seen), scanned.listed_parents):
            continue
        posture = covered(path)
        if posture is None:
            continue
        events.append(
            {
                "relative_path": path,
                "operation": "delete",
                "outcome": "detected",
                "origin_detail": UNDETERMINED,
                "preventive": False,
                "severity": "high",
                "explanation": UNDETERMINED_EXPLANATION,
                "action_taken": "Se registró la ausencia después de ocurrir. No se restauró el archivo.",
            }
        )
    return events


def poll(root: Path, previous: dict[str, tuple], covered) -> tuple[Scan, list[dict]]:
    scanned = scan_tree(root)
    return scanned, diff(previous, scanned, covered)
