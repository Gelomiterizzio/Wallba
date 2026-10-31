"""SQLite propio del estado de protección, fuera del proyecto analizado."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    canonical_root TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    last_scan_at TEXT,
    watch_enabled INTEGER NOT NULL DEFAULT 0,
    watch_error TEXT,
    last_poll_at TEXT,
    files_scanned INTEGER NOT NULL DEFAULT 0,
    directories_scanned INTEGER NOT NULL DEFAULT 0,
    truncated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS entries (
    project_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    parent_path TEXT NOT NULL,
    name TEXT NOT NULL,
    entry_kind TEXT NOT NULL,
    risk TEXT NOT NULL,
    category TEXT NOT NULL,
    reasons TEXT NOT NULL,
    size_bytes INTEGER,
    mtime_ns INTEGER,
    excluded INTEGER NOT NULL DEFAULT 0,
    extension TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (project_id, relative_path),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS entries_parent ON entries(project_id, parent_path);
CREATE TABLE IF NOT EXISTS exclusions (
    project_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    PRIMARY KEY (project_id, relative_path),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    entry_kind TEXT NOT NULL,
    recursive INTEGER NOT NULL,
    policy TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, relative_path),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    severity TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    operation TEXT NOT NULL,
    outcome TEXT NOT NULL,
    origin TEXT NOT NULL,
    origin_detail TEXT NOT NULL,
    explanation TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '',
    read_at TEXT,
    fingerprint TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS events_lookup ON events(project_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS events_fp ON events(fingerprint, occurred_at);
CREATE TABLE IF NOT EXISTS integrity (
    project_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    note TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, relative_path),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""

EVENT_CAP = 5000


@dataclass(frozen=True)
class ProjectRow:
    id: str
    canonical_root: str
    display_name: str
    opened_at: str
    last_scan_at: str | None
    watch_enabled: bool
    watch_error: str | None
    last_poll_at: str | None
    files_scanned: int
    directories_scanned: int
    truncated: bool


def _project(row: sqlite3.Row) -> ProjectRow:
    return ProjectRow(
        id=row["id"],
        canonical_root=row["canonical_root"],
        display_name=row["display_name"],
        opened_at=row["opened_at"],
        last_scan_at=row["last_scan_at"],
        watch_enabled=bool(row["watch_enabled"]),
        watch_error=row["watch_error"],
        last_poll_at=row["last_poll_at"],
        files_scanned=row["files_scanned"],
        directories_scanned=row["directories_scanned"],
        truncated=bool(row["truncated"]),
    )


class ProtectionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("PRAGMA user_version = 1")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()

    def upsert_project(
        self,
        *,
        project_id: str,
        canonical_root: str,
        display_name: str,
        opened_at: str,
        last_scan_at: str,
        files_scanned: int,
        directories_scanned: int,
        truncated: bool,
    ) -> None:
        with self._tx() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, canonical_root, display_name, opened_at, last_scan_at,
                    files_scanned, directories_scanned, truncated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_root) DO UPDATE SET
                    last_scan_at = excluded.last_scan_at,
                    files_scanned = excluded.files_scanned,
                    directories_scanned = excluded.directories_scanned,
                    truncated = excluded.truncated,
                    display_name = excluded.display_name
                """,
                (
                    project_id,
                    canonical_root,
                    display_name,
                    opened_at,
                    last_scan_at,
                    files_scanned,
                    directories_scanned,
                    int(truncated),
                ),
            )

    def get_project(self, project_id: str) -> ProjectRow | None:
        with self._tx() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return _project(row) if row else None

    def get_by_root(self, canonical_root: str) -> ProjectRow | None:
        with self._tx() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE canonical_root = ?", (canonical_root,)
            ).fetchone()
        return _project(row) if row else None

    def list_projects(self) -> list[ProjectRow]:
        with self._tx() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY opened_at DESC").fetchall()
        return [_project(row) for row in rows]

    def set_watch(self, project_id: str, enabled: bool, error: str | None) -> None:
        with self._tx() as connection:
            connection.execute(
                "UPDATE projects SET watch_enabled = ?, watch_error = ? WHERE id = ?",
                (int(enabled), error, project_id),
            )

    def mark_poll(self, project_id: str, at: str, error: str | None) -> None:
        with self._tx() as connection:
            connection.execute(
                "UPDATE projects SET last_poll_at = ?, watch_error = ? WHERE id = ?",
                (at, error, project_id),
            )

    def replace_entries(self, project_id: str, rows: list[tuple]) -> None:
        with self._tx() as connection:
            excluded = {
                row[0]
                for row in connection.execute(
                    "SELECT relative_path FROM exclusions WHERE project_id = ?", (project_id,)
                )
            }
            connection.execute("DELETE FROM entries WHERE project_id = ?", (project_id,))
            payload = []
            for row in rows:
                relative = row[0]
                payload.append((*row, int(relative in excluded or _child_of(relative, excluded))))
            connection.executemany(
                """
                INSERT INTO entries (
                    project_id, relative_path, parent_path, name, entry_kind, risk, category,
                    reasons, size_bytes, mtime_ns, extension, excluded
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(project_id, *item) for item in payload],
            )

    def list_children(self, project_id: str, parent_path: str) -> list[sqlite3.Row]:
        with self._tx() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM entries
                    WHERE project_id = ? AND parent_path = ?
                    ORDER BY entry_kind = 'file', name
                    """,
                    (project_id, parent_path),
                )
            )

    def parents_with_children(self, project_id: str, parents: list[str]) -> set[str]:
        if not parents:
            return set()
        marks = ",".join("?" for _ in parents)
        with self._tx() as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT parent_path FROM entries
                WHERE project_id = ? AND parent_path IN ({marks})
                """,
                (project_id, *parents),
            ).fetchall()
        return {row["parent_path"] for row in rows}

    def search(self, project_id: str, query: str, extension: str, risk: str, limit: int) -> list[sqlite3.Row]:
        clauses = ["project_id = ?"]
        params: list[object] = [project_id]
        if query:
            clauses.append("(instr(lower(relative_path), lower(?)) > 0 OR instr(lower(name), lower(?)) > 0)")
            params.extend([query, query])
        if extension:
            clauses.append("extension = ?")
            params.append(extension.lower().lstrip("."))
        if risk:
            clauses.append("risk = ?")
            params.append(risk)
        params.append(limit)
        with self._tx() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT * FROM entries
                    WHERE {' AND '.join(clauses)}
                    ORDER BY CASE risk
                        WHEN 'CRITICAL' THEN 0
                        WHEN 'HIGH' THEN 1
                        WHEN 'MEDIUM' THEN 2
                        ELSE 3
                    END, relative_path
                    LIMIT ?
                    """,
                    params,
                )
            )

    def get_entry(self, project_id: str, relative_path: str) -> sqlite3.Row | None:
        with self._tx() as connection:
            return connection.execute(
                "SELECT * FROM entries WHERE project_id = ? AND relative_path = ?",
                (project_id, relative_path),
            ).fetchone()

    def upsert_entry(self, project_id: str, row: tuple, excluded: bool) -> None:
        with self._tx() as connection:
            connection.execute(
                """
                INSERT INTO entries (
                    project_id, relative_path, parent_path, name, entry_kind, risk, category,
                    reasons, size_bytes, mtime_ns, extension, excluded
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, relative_path) DO UPDATE SET
                    risk = excluded.risk,
                    category = excluded.category,
                    reasons = excluded.reasons,
                    size_bytes = excluded.size_bytes,
                    mtime_ns = excluded.mtime_ns,
                    extension = excluded.extension,
                    entry_kind = excluded.entry_kind,
                    excluded = excluded.excluded
                """,
                (project_id, *row, int(excluded)),
            )

    def update_stamp(self, project_id: str, relative_path: str, size: int | None, mtime_ns: int | None) -> None:
        with self._tx() as connection:
            connection.execute(
                "UPDATE entries SET size_bytes = ?, mtime_ns = ? WHERE project_id = ? AND relative_path = ?",
                (size, mtime_ns, project_id, relative_path),
            )

    def delete_entry(self, project_id: str, relative_path: str) -> None:
        prefix = relative_path + "/"
        with self._tx() as connection:
            paths = [
                row["relative_path"]
                for row in connection.execute(
                    "SELECT relative_path FROM entries WHERE project_id = ?", (project_id,)
                )
                if row["relative_path"] == relative_path or row["relative_path"].startswith(prefix)
            ]
            for path in paths:
                connection.execute(
                    "DELETE FROM entries WHERE project_id = ? AND relative_path = ?",
                    (project_id, path),
                )

    def iter_entries(self, project_id: str) -> list[sqlite3.Row]:
        with self._tx() as connection:
            return list(connection.execute("SELECT * FROM entries WHERE project_id = ?", (project_id,)))

    def exclusion_set(self, project_id: str) -> set[str]:
        with self._tx() as connection:
            rows = connection.execute(
                "SELECT relative_path FROM exclusions WHERE project_id = ?", (project_id,)
            ).fetchall()
        return {row["relative_path"] for row in rows}

    def set_exclusion(self, project_id: str, paths: list[str], excluded: bool) -> None:
        with self._tx() as connection:
            for path in paths:
                if excluded:
                    connection.execute(
                        "INSERT OR IGNORE INTO exclusions (project_id, relative_path) VALUES (?, ?)",
                        (project_id, path),
                    )
                else:
                    connection.execute(
                        "DELETE FROM exclusions WHERE project_id = ? AND relative_path = ?",
                        (project_id, path),
                    )
            flags = {
                row[0]
                for row in connection.execute(
                    "SELECT relative_path FROM exclusions WHERE project_id = ?", (project_id,)
                )
            }
            for row in connection.execute(
                "SELECT relative_path FROM entries WHERE project_id = ?", (project_id,)
            ):
                path = row["relative_path"]
                connection.execute(
                    "UPDATE entries SET excluded = ? WHERE project_id = ? AND relative_path = ?",
                    (int(_child_of(path, flags) or path in flags), project_id, path),
                )

    def clear_exclusion(self, project_id: str, path: str) -> None:
        self.set_exclusion(project_id, [path], False)

    def list_rules(self, project_id: str) -> list[sqlite3.Row]:
        with self._tx() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM rules WHERE project_id = ? ORDER BY relative_path", (project_id,)
                )
            )

    def upsert_rule(self, row: tuple) -> None:
        with self._tx() as connection:
            connection.execute(
                """
                INSERT INTO rules (
                    id, project_id, relative_path, entry_kind, recursive, policy, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, relative_path) DO UPDATE SET
                    entry_kind = excluded.entry_kind,
                    recursive = excluded.recursive,
                    policy = excluded.policy,
                    updated_at = excluded.updated_at
                """,
                row,
            )

    def delete_rules(self, project_id: str, rule_ids: list[str]) -> int:
        if not rule_ids:
            return 0
        marks = ",".join("?" for _ in rule_ids)
        with self._tx() as connection:
            cursor = connection.execute(
                f"DELETE FROM rules WHERE project_id = ? AND id IN ({marks})",
                (project_id, *rule_ids),
            )
            return cursor.rowcount

    def add_event(self, row: tuple, *, dedup: bool, dedup_after: str) -> bool:
        with self._tx() as connection:
            if dedup:
                found = connection.execute(
                    """
                    SELECT 1 FROM events
                    WHERE fingerprint = ? AND occurred_at >= ?
                    LIMIT 1
                    """,
                    (row[-1], dedup_after),
                ).fetchone()
                if found:
                    return False
            connection.execute(
                """
                INSERT INTO events (
                    id, project_id, occurred_at, severity, relative_path, operation, outcome,
                    origin, origin_detail, explanation, action_taken, evidence, fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            connection.execute(
                """
                DELETE FROM events WHERE project_id = ? AND id IN (
                    SELECT id FROM events WHERE project_id = ?
                    ORDER BY occurred_at DESC LIMIT -1 OFFSET ?
                )
                """,
                (row[1], row[1], EVENT_CAP),
            )
            return True

    def list_events(
        self,
        project_id: str,
        *,
        severity: str,
        outcome: str,
        query: str,
        unread: bool,
        limit: int,
    ) -> list[sqlite3.Row]:
        clauses = ["project_id = ?"]
        params: list[object] = [project_id]
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if outcome:
            clauses.append("outcome = ?")
            params.append(outcome)
        if query:
            clauses.append("instr(lower(relative_path), lower(?)) > 0")
            params.append(query)
        if unread:
            clauses.append("read_at IS NULL")
        params.append(limit)
        with self._tx() as connection:
            return list(
                connection.execute(
                    f"""
                    SELECT * FROM events
                    WHERE {' AND '.join(clauses)}
                    ORDER BY occurred_at DESC
                    LIMIT ?
                    """,
                    params,
                )
            )

    def count_unread(self, project_id: str) -> int:
        with self._tx() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM events WHERE project_id = ? AND read_at IS NULL",
                (project_id,),
            ).fetchone()
        return int(row["total"])

    def count_outcomes(self, project_id: str) -> dict[str, int]:
        with self._tx() as connection:
            rows = connection.execute(
                """
                SELECT outcome, COUNT(*) AS total FROM events
                WHERE project_id = ? GROUP BY outcome
                """,
                (project_id,),
            ).fetchall()
        return {row["outcome"]: row["total"] for row in rows}

    def mark_read(self, project_id: str, ids: list[str] | None, at: str) -> int:
        with self._tx() as connection:
            if ids is None:
                cursor = connection.execute(
                    "UPDATE events SET read_at = ? WHERE project_id = ? AND read_at IS NULL",
                    (at, project_id),
                )
            elif not ids:
                return 0
            else:
                marks = ",".join("?" for _ in ids)
                cursor = connection.execute(
                    f"""
                    UPDATE events SET read_at = ?
                    WHERE project_id = ? AND id IN ({marks}) AND read_at IS NULL
                    """,
                    (at, project_id, *ids),
                )
            return cursor.rowcount

    def upsert_integrity(self, row: tuple) -> None:
        with self._tx() as connection:
            connection.execute(
                """
                INSERT INTO integrity (
                    project_id, relative_path, sha256, size_bytes, mtime_ns, note, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, relative_path) DO UPDATE SET
                    sha256 = excluded.sha256,
                    size_bytes = excluded.size_bytes,
                    mtime_ns = excluded.mtime_ns,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                row,
            )

    def list_integrity(self, project_id: str) -> list[sqlite3.Row]:
        with self._tx() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM integrity WHERE project_id = ?", (project_id,)
                )
            )

    def get_integrity(self, project_id: str, relative_path: str) -> sqlite3.Row | None:
        with self._tx() as connection:
            return connection.execute(
                "SELECT * FROM integrity WHERE project_id = ? AND relative_path = ?",
                (project_id, relative_path),
            ).fetchone()

    def delete_integrity(self, project_id: str, relative_path: str) -> None:
        with self._tx() as connection:
            connection.execute(
                "DELETE FROM integrity WHERE project_id = ? AND relative_path = ?",
                (project_id, relative_path),
            )

    def stamps(self, project_id: str) -> dict[str, tuple[int | None, int | None, str]]:
        with self._tx() as connection:
            rows = connection.execute(
                "SELECT relative_path, mtime_ns, size_bytes, entry_kind FROM entries WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return {
            row["relative_path"]: (row["mtime_ns"], row["size_bytes"], row["entry_kind"]) for row in rows
        }


def _child_of(path: str, parents: set[str]) -> bool:
    return any(path.startswith(parent + "/") for parent in parents)


def reasons_json(reasons: tuple[str, ...] | list[str]) -> str:
    return json.dumps(list(reasons), ensure_ascii=False)
