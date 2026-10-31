"""Une escaneo, políticas, shim y monitor para un proyecto."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from wallba.guard.errors import GuardError
from wallba.guard.monitor import poll
from wallba.guard.paths import assert_separated, canonical_directory, resolve_inside
from wallba.guard.policy import KNOWN, decide
from wallba.guard.scanner import scan_tree
from wallba.guard.shim import attempt
from wallba.guard.store import GuardStore

INSTRUMENTED = "wallba-test-agent"


class GuardRuntime:
    def __init__(self, db_path: Path, state_dir: Path) -> None:
        self.store = GuardStore(db_path)
        self.state_dir = state_dir
        self._snapshots: dict[str, dict[str, tuple]] = {}

    def create_sample(self) -> dict:
        root = self.state_dir.parent / "samples" / "synthetic-risk-project"
        files = {
            "README.md": "Proyecto sintético de WALLBA. No contiene secretos reales.\n",
            "src/app.py": "def main():\n    return 'ok'\n",
            "src/token_helper.py": "VALUE = 'not-a-secret'\n",
            "config/.env": "DEMO_TOKEN=ejemplo-ficticio-no-usar\n",
            "data/backup.sql": "-- volcado ficticio\nSELECT 1;\n",
        }
        for relative, text in files.items():
            path = root.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return self.open_project(str(root))

    def open_project(self, raw: str) -> dict:
        root = canonical_directory(raw)
        assert_separated(root, self.state_dir)
        scanned = scan_tree(root)
        now = _now()
        project_id = self.store.save_project(
            project_id=str(uuid.uuid4()),
            root=str(root),
            name=root.name,
            opened_at=now,
            files=scanned.files,
            directories=scanned.directories,
            truncated=scanned.truncated,
        )
        self.store.replace_entries(project_id, scanned.entries)
        self._snapshots[project_id] = self.store.stamps(project_id)
        return self.summary(project_id)

    def summary(self, project_id: str) -> dict:
        project = self._require(project_id)
        counts = self.store.count_events(project_id)
        risks = self.store.risk_counts(project_id)
        rules = self.store.rules(project_id)
        protected = 0
        for rule in rules:
            protected += 1
        return {
            "project": _project_dict(project),
            "files_scanned": project["files_scanned"],
            "directories_scanned": project["directories_scanned"],
            "truncated": bool(project["truncated"]),
            "by_risk": {level: risks.get(level, 0) for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")},
            "rules": len(rules),
            "protected_entries": protected,
            "events": {
                "blocked": counts.get("blocked", 0),
                "observed": counts.get("observed", 0),
                "detected": counts.get("detected", 0),
                "allowed_unprotected": counts.get("allowed_unprotected", 0),
            },
            "monitoring": {
                "enabled": bool(project["watch_enabled"]),
                "error": project["watch_error"],
                "preventive": "solo el agente instrumentado wallba-test-agent, y solo si la política es de bloqueo",
                "observation": "el monitor registra cambios posteriores y no identifica al autor",
            },
            "supervised_agents": [
                {
                    "id": INSTRUMENTED,
                    "kind": "instrumented",
                    "note": "Solo existe cuando WALLBA ejecuta el shim o el hook. No representa a otro programa.",
                }
            ],
        }

    def children(self, project_id: str, parent: str) -> list[dict]:
        self._require(project_id)
        if parent:
            root = Path(self._require(project_id)["canonical_root"])
            resolve_inside(root, parent)
        rows = self.store.children(project_id, parent)
        rules = self.store.rules(project_id)
        return [_entry_dict(row, _posture(row["relative_path"], rules)) for row in rows]

    def protect(self, project_id: str, relative_path: str, kind: str, posture: str) -> None:
        if posture not in KNOWN:
            raise GuardError("POSTURE_UNKNOWN", "La política no se reconoce. No se aplicó.")
        project = self._require(project_id)
        target = resolve_inside(Path(project["canonical_root"]), relative_path)
        actual = "directory" if target.is_dir() else "file"
        if kind != actual:
            raise GuardError("KIND_MISMATCH", "El tipo no coincide con la ruta.")
        relative = target.resolve().relative_to(Path(project["canonical_root"]).resolve()).as_posix()
        self.store.upsert_rule(project_id, relative, actual, actual == "directory", posture)
        self._record(
            project_id,
            relative,
            "policy_change",
            "recorded",
            "info",
            "operador",
            "Un operador cambió la política.",
            f"Política {posture} guardada.",
            False,
        )

    def remove_rule(self, project_id: str, rule_id: str) -> None:
        self._require(project_id)
        if self.store.delete_rule(project_id, rule_id) != 1:
            raise GuardError("RULE_NOT_FOUND", "La regla no existe.", 404)

    def probe(self, project_id: str, relative_path: str, operation: str, *, apply: bool, content: str | None) -> dict:
        project = self._require(project_id)
        root = Path(project["canonical_root"])
        target = resolve_inside(root, relative_path)
        if target.is_dir():
            raise GuardError("NOT_A_FILE", "El agente de prueba actúa sobre archivos.")
        relative = target.resolve().relative_to(root.resolve()).as_posix()
        posture = _posture(relative, self.store.rules(project_id))
        payload = None if content is None else content.encode("utf-8")
        if payload is not None and (b"\x00" in payload or len(payload) > 200):
            raise GuardError("CONTENT_REJECTED", "El contenido de prueba no es válido.")
        result = attempt(root, target, posture, operation, apply=apply, content=payload)
        self._record(
            project_id,
            relative,
            operation,
            result["outcome"],
            "critical" if result["outcome"] == "blocked" else "medium" if posture == "alert" else "low",
            result["origin_detail"],
            result["reason"],
            result["reason"],
            bool(result["preventive"]),
        )
        if result["changed"] and operation == "write" and target.exists():
            stat = target.stat()
            self.store.update_stamp(project_id, relative, stat.st_size, stat.st_mtime_ns)
            snap = self._snapshots.setdefault(project_id, {})
            snap[relative] = (stat.st_mtime_ns, stat.st_size, "file")
        result["preventive"] = bool(result["preventive"])
        result["relative_path"] = relative
        return result

    def watch_once(self, project_id: str) -> list[dict]:
        project = self._require(project_id)
        root = Path(project["canonical_root"])
        previous = self._snapshots.setdefault(project_id, self.store.stamps(project_id))
        rules = self.store.rules(project_id)
        _scanned, found = poll(root, previous, lambda path: _posture(path, rules))
        for item in found:
            self._record(
                project_id,
                item["relative_path"],
                item["operation"],
                item["outcome"],
                item["severity"],
                item["origin_detail"],
                item["explanation"],
                item["action_taken"],
                False,
            )
        self._snapshots[project_id] = self.store.stamps(project_id)
        fresh = scan_tree(root)
        self.store.replace_entries(project_id, fresh.entries)
        self._snapshots[project_id] = {
            item.relative_path: (item.mtime_ns, item.size_bytes, item.kind) for item in fresh.entries
        }
        return found

    def events(self, project_id: str) -> list[dict]:
        self._require(project_id)
        return [_event_dict(row) for row in self.store.events(project_id)]

    def _require(self, project_id: str):
        project = self.store.project(project_id)
        if project is None:
            raise GuardError("PROJECT_NOT_FOUND", "El proyecto no está abierto.", 404)
        return project

    def _record(self, project_id, path, operation, outcome, severity, origin, explanation, action, preventive) -> None:
        self.store.add_event(
            (
                str(uuid.uuid4()),
                project_id,
                _now(),
                severity,
                path,
                operation,
                outcome,
                origin,
                explanation,
                action,
                int(preventive),
            )
        )


def posture_for_filesystem_path(db_path: Path, raw_path: str) -> str | None:
    store = GuardStore(db_path)
    try:
        candidate = Path(raw_path).resolve(strict=False)
    except OSError:
        return "unknown"
    chosen = None
    for project in store.projects():
        root = Path(project["canonical_root"]).resolve()
        if candidate != root and not candidate.is_relative_to(root):
            continue
        relative = candidate.relative_to(root).as_posix() if candidate != root else ""
        if relative == "":
            continue
        posture = _posture(relative, store.rules(project["id"]))
        if posture is not None:
            chosen = _stricter(chosen, posture)
    return chosen


def _stricter(left: str | None, right: str) -> str:
    rank = {"monitor": 1, "alert": 2, "block_read": 3, "block_write": 3, "block_all": 4}
    if left is None or rank.get(right, 0) > rank.get(left, 0):
        return right
    return left


def _posture(relative: str, rules) -> str | None:
    matched = []
    for rule in rules:
        rule_path = rule["relative_path"]
        if rule_path == relative or (rule["recursive"] and relative.startswith(rule_path + "/")):
            matched.append(rule["posture"])
    if not matched:
        return None
    chosen = None
    for posture in matched:
        chosen = _stricter(chosen, posture)
    if "block_read" in matched and "block_write" in matched:
        return "block_all"
    return chosen


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_dict(row) -> dict:
    return {
        "id": row["id"],
        "canonical_root": row["canonical_root"],
        "display_name": row["display_name"],
        "opened_at": row["opened_at"],
        "watch_enabled": bool(row["watch_enabled"]),
    }


def _entry_dict(row, posture: str | None) -> dict:
    import json

    decision = decide(posture, "read")
    return {
        "path": row["relative_path"],
        "name": row["name"],
        "kind": row["entry_kind"],
        "risk": row["risk"],
        "category": row["category"],
        "reasons": json.loads(row["reasons"]),
        "posture": posture,
        "preventive": decision.preventive,
    }


def _event_dict(row) -> dict:
    return {
        "id": row["id"],
        "occurred_at": row["occurred_at"],
        "severity": row["severity"],
        "relative_path": row["relative_path"],
        "operation": row["operation"],
        "outcome": row["outcome"],
        "origin_detail": row["origin_detail"],
        "explanation": row["explanation"],
        "action_taken": row["action_taken"],
        "preventive": bool(row["preventive"]),
    }
