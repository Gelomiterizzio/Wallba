"""Estado del guardia, fuera de la carpeta analizada."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from wallba.guard.scanner import Entry

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    canonical_root TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    files_scanned INTEGER NOT NULL,
    directories_scanned INTEGER NOT NULL,
    truncated INTEGER NOT NULL,
    watch_enabled INTEGER NOT NULL DEFAULT 0,
    watch_error TEXT
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
    PRIMARY KEY (project_id, relative_path)
);
CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    entry_kind TEXT NOT NULL,
    recursive INTEGER NOT NULL,
    posture TEXT NOT NULL,
    UNIQUE (project_id, relative_path)
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    severity TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    operation TEXT NOT NULL,
    outcome TEXT NOT NULL,
    origin_detail TEXT NOT NULL,
    explanation TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    preventive INTEGER NOT NULL,
    read_at TEXT
);
"""


class GuardStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

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

    def save_project(self, *, project_id: str, root: str, name: str, opened_at: str, files: int, directories: int, truncated: bool) -> str:
        with self._tx() as connection:
            existing = connection.execute("SELECT id FROM projects WHERE canonical_root = ?", (root,)).fetchone()
            kept = existing["id"] if existing else project_id
            connection.execute(
                """
                INSERT INTO projects (id, canonical_root, display_name, opened_at, files_scanned, directories_scanned, truncated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_root) DO UPDATE SET
                    display_name = excluded.display_name,
                    files_scanned = excluded.files_scanned,
                    directories_scanned = excluded.directories_scanned,
                    truncated = excluded.truncated
                """,
                (kept, root, name, opened_at, files, directories, int(truncated)),
            )
            return kept

    def replace_entries(self, project_id: str, entries: tuple[Entry, ...]) -> None:
        with self._tx() as connection:
            connection.execute("DELETE FROM entries WHERE project_id = ?", (project_id,))
            connection.executemany(
                """
                INSERT INTO entries (
                    project_id, relative_path, parent_path, name, entry_kind, risk, category, reasons, size_bytes, mtime_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        project_id,
                        item.relative_path,
                        item.parent_path,
                        item.name,
                        item.kind,
                        item.classification.risk,
                        item.classification.category,
                        json.dumps(list(item.classification.reasons), ensure_ascii=False),
                        item.size_bytes,
                        item.mtime_ns,
                    )
                    for item in entries
                ],
            )

    def project(self, project_id: str) -> sqlite3.Row | None:
        with self._tx() as connection:
            return connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()

    def projects(self) -> list[sqlite3.Row]:
        with self._tx() as connection:
            return list(connection.execute("SELECT * FROM projects ORDER BY opened_at DESC"))

    def children(self, project_id: str, parent: str) -> list[sqlite3.Row]:
        with self._tx() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM entries WHERE project_id = ? AND parent_path = ?
                    ORDER BY entry_kind = 'file', name
                    """,
                    (project_id, parent),
                )
            )

    def rules(self, project_id: str) -> list[sqlite3.Row]:
        with self._tx() as connection:
            return list(connection.execute("SELECT * FROM rules WHERE project_id = ? ORDER BY relative_path", (project_id,)))

    def upsert_rule(self, project_id: str, relative_path: str, kind: str, recursive: bool, posture: str) -> None:
        with self._tx() as connection:
            connection.execute(
                """
                INSERT INTO rules (id, project_id, relative_path, entry_kind, recursive, posture)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, relative_path) DO UPDATE SET
                    entry_kind = excluded.entry_kind,
                    recursive = excluded.recursive,
                    posture = excluded.posture
                """,
                (str(uuid.uuid4()), project_id, relative_path, kind, int(recursive), posture),
            )

    def delete_rule(self, project_id: str, rule_id: str) -> int:
        with self._tx() as connection:
            return connection.execute(
                "DELETE FROM rules WHERE project_id = ? AND id = ?", (project_id, rule_id)
            ).rowcount

    def add_event(self, row: tuple) -> None:
        with self._tx() as connection:
            connection.execute(
                """
                INSERT INTO events (
                    id, project_id, occurred_at, severity, relative_path, operation, outcome,
                    origin_detail, explanation, action_taken, preventive
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

    def events(self, project_id: str, limit: int = 100) -> list[sqlite3.Row]:
        with self._tx() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM events WHERE project_id = ? ORDER BY occurred_at DESC LIMIT ?",
                    (project_id, limit),
                )
            )

    def count_events(self, project_id: str) -> dict[str, int]:
        with self._tx() as connection:
            rows = connection.execute(
                "SELECT outcome, COUNT(*) AS total FROM events WHERE project_id = ? GROUP BY outcome",
                (project_id,),
            )
            return {row["outcome"]: row["total"] for row in rows}

    def set_watch(self, project_id: str, enabled: bool, error: str | None = None) -> None:
        with self._tx() as connection:
            connection.execute(
                "UPDATE projects SET watch_enabled = ?, watch_error = ? WHERE id = ?",
                (int(enabled), error, project_id),
            )

    def stamps(self, project_id: str) -> dict[str, tuple[int | None, int | None, str]]:
        with self._tx() as connection:
            rows = connection.execute(
                "SELECT relative_path, mtime_ns, size_bytes, entry_kind FROM entries WHERE project_id = ?",
                (project_id,),
            )
            return {row["relative_path"]: (row["mtime_ns"], row["size_bytes"], row["entry_kind"]) for row in rows}

    def update_stamp(self, project_id: str, relative_path: str, size: int | None, mtime: int | None) -> None:
        with self._tx() as connection:
            connection.execute(
                "UPDATE entries SET size_bytes = ?, mtime_ns = ? WHERE project_id = ? AND relative_path = ?",
                (size, mtime, project_id, relative_path),
            )

    def risk_counts(self, project_id: str) -> dict[str, int]:
        with self._tx() as connection:
            rows = connection.execute(
                """
                SELECT risk, COUNT(*) AS total FROM entries
                WHERE project_id = ? AND entry_kind = 'file' GROUP BY risk
                """,
                (project_id,),
            )
            return {row["risk"]: row["total"] for row in rows}
