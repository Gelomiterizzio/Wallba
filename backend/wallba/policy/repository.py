"""Versiones inmutables y puntero activo con compare-and-swap.

Usa sqlite3 de la biblioteca estándar y el esquema de docs/DATABASE_DESIGN.md.
La migración Alembic y el lock de SQLAlchemy pertenecen a Persona 1; este
adaptador cubre el puerto mientras esa base no existe.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

from wallba.policy.models import MAX_VERSION, SLUG, PolicyDocument, PolicySnapshot
from wallba.policy.schemas import canonical_bytes, snapshot_from_document, validate_mapping

_CREATED_AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

SCHEMA_SQL = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
_SCHEMA = SCHEMA_SQL


class VersionConflict(Exception):
    """(policy_id, version) ya existe. No se sobrescribe."""


class ActivationConflict(Exception):
    """La versión esperada no coincide con el puntero activo."""


class VersionNotFound(Exception):
    pass


class PolicyStorageError(Exception):
    pass


class AuditFailure(Exception):
    pass


class InvalidCursor(Exception):
    pass


class AuditSink(Protocol):
    def append(self, event: Mapping[str, object], connection: object) -> None:
        """Registra dentro de la transacción. Si falla, la activación aborta."""


@dataclass(frozen=True)
class VersionSummary:
    policy_id: str
    version: int
    checksum: str
    created_by: str
    created_at: str
    active: bool


@dataclass(frozen=True)
class VersionRecord:
    summary: VersionSummary
    document: PolicyDocument


@dataclass(frozen=True)
class VersionPage:
    items: tuple[VersionSummary, ...]
    next_cursor: str | None


class SqlitePolicyRepository:
    def __init__(self, database_path: str | Path) -> None:
        self._path = str(database_path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure()

    def save_version(self, document: PolicyDocument, created_by: str, created_at: str) -> VersionSummary:
        if not _CREATED_AT.fullmatch(created_at):
            raise PolicyStorageError()
        payload = canonical_bytes(document)
        checksum = hashlib.sha256(payload).hexdigest()
        text = payload.decode("utf-8")
        with self._connection() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                con.execute(
                    """
                    INSERT INTO policy_versions
                        (policy_id, version, normalized_json, checksum, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (document.policy_id, document.version, text, checksum, created_by, created_at),
                )
                con.execute("COMMIT")
            except sqlite3.IntegrityError:
                _rollback(con)
                raise VersionConflict()
            except sqlite3.Error as exc:
                _rollback(con)
                raise PolicyStorageError() from exc
        return VersionSummary(
            policy_id=document.policy_id,
            version=document.version,
            checksum=checksum,
            created_by=created_by,
            created_at=created_at,
            active=False,
        )

    def activate(
        self,
        policy_id: str,
        version: int,
        expected_active_version: int | None,
        actor_id: str,
        occurred_at: str,
        audit: AuditSink,
        expected_active_policy_id: str | None = None,
    ) -> PolicySnapshot:
        if not _CREATED_AT.fullmatch(occurred_at):
            raise PolicyStorageError()
        if expected_active_version is not None and (
            isinstance(expected_active_version, bool) or not isinstance(expected_active_version, int)
        ):
            raise ActivationConflict()
        with self._connection() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                current = con.execute(
                    "SELECT policy_id, version FROM policy_activation WHERE singleton_id = 1"
                ).fetchone()
                current_policy_id = None if current is None else str(current["policy_id"])
                current_version = None if current is None else int(current["version"])
                if expected_active_version != current_version:
                    raise ActivationConflict()
                # El número de versión no identifica la política activa: other-policy v1
                # no puede sustituir a demo-policy v1 solo porque ambas son la versión 1.
                if current_policy_id is None:
                    if expected_active_policy_id is not None:
                        raise ActivationConflict()
                elif expected_active_policy_id not in (None, current_policy_id):
                    raise ActivationConflict()
                elif current_policy_id != policy_id and expected_active_policy_id != current_policy_id:
                    raise ActivationConflict()
                row = con.execute(
                    """
                    SELECT normalized_json, checksum FROM policy_versions
                    WHERE policy_id = ? AND version = ?
                    """,
                    (policy_id, version),
                ).fetchone()
                if row is None:
                    raise VersionNotFound()
                document = _load_stored(row)
                snapshot = snapshot_from_document(document)
                if current is None:
                    con.execute(
                        """
                        INSERT INTO policy_activation (singleton_id, policy_id, version, revision)
                        VALUES (1, ?, ?, 1)
                        """,
                        (policy_id, version),
                    )
                else:
                    updated = con.execute(
                        """
                        UPDATE policy_activation
                        SET policy_id = ?, version = ?, revision = revision + 1
                        WHERE singleton_id = 1 AND policy_id = ? AND version = ?
                        """,
                        (policy_id, version, current_policy_id, expected_active_version),
                    )
                    if updated.rowcount != 1:
                        raise ActivationConflict()
                audit.append(
                    {
                        "event_type": "policy_activated",
                        "policy_id": policy_id,
                        "policy_version": version,
                        "checksum": snapshot.checksum,
                        "actor_id": actor_id,
                        "occurred_at": occurred_at,
                    },
                    con,
                )
                con.execute("COMMIT")
                return snapshot
            except (ActivationConflict, VersionNotFound, AuditFailure):
                _rollback(con)
                raise
            except sqlite3.IntegrityError:
                _rollback(con)
                raise ActivationConflict()
            except sqlite3.Error as exc:
                _rollback(con)
                raise PolicyStorageError() from exc
            except Exception:
                _rollback(con)
                raise

    def get_active_snapshot(self) -> PolicySnapshot | None:
        with self._connection() as con:
            con.execute("BEGIN")
            try:
                current = con.execute(
                    "SELECT policy_id, version FROM policy_activation WHERE singleton_id = 1"
                ).fetchone()
                if current is None:
                    con.execute("COMMIT")
                    return None
                row = con.execute(
                    """
                    SELECT normalized_json, checksum FROM policy_versions
                    WHERE policy_id = ? AND version = ?
                    """,
                    (current["policy_id"], current["version"]),
                ).fetchone()
                con.execute("COMMIT")
            except sqlite3.Error as exc:
                _rollback(con)
                raise PolicyStorageError() from exc
        if row is None:
            raise PolicyStorageError()
        return snapshot_from_document(_load_stored(row))

    def get_version(self, policy_id: str, version: int) -> VersionRecord | None:
        with self._connection() as con:
            row = con.execute(
                """
                SELECT v.policy_id, v.version, v.checksum, v.created_by, v.created_at, v.normalized_json,
                       CASE WHEN a.policy_id IS NOT NULL THEN 1 ELSE 0 END AS active
                FROM policy_versions v
                LEFT JOIN policy_activation a
                  ON a.singleton_id = 1 AND a.policy_id = v.policy_id AND a.version = v.version
                WHERE v.policy_id = ? AND v.version = ?
                """,
                (policy_id, version),
            ).fetchone()
        if row is None:
            return None
        document = _load_stored(row)
        return VersionRecord(summary=_summary(row), document=document)

    def list_versions(self, cursor: str | None, limit: int) -> VersionPage:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise InvalidCursor()
        decoded = None if cursor is None else _decode_cursor(cursor)
        with self._connection() as con:
            if decoded is None:
                rows = con.execute(
                    _LIST_SQL + " ORDER BY v.created_at DESC, v.policy_id DESC, v.version DESC LIMIT ?",
                    (limit + 1,),
                ).fetchall()
            else:
                created_at, policy_id, version = decoded
                rows = con.execute(
                    _LIST_SQL
                    + """
                    WHERE v.created_at < ?
                       OR (v.created_at = ? AND v.policy_id < ?)
                       OR (v.created_at = ? AND v.policy_id = ? AND v.version < ?)
                    ORDER BY v.created_at DESC, v.policy_id DESC, v.version DESC
                    LIMIT ?
                    """,
                    (created_at, created_at, policy_id, created_at, policy_id, version, limit + 1),
                ).fetchall()
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit and page:
            last = page[-1]
            next_cursor = _encode_cursor(last["created_at"], last["policy_id"], int(last["version"]))
        return VersionPage(items=tuple(_summary(row) for row in page), next_cursor=next_cursor)

    def _ensure(self) -> None:
        with self._connection() as con:
            con.executescript(_SCHEMA)
            con.execute("PRAGMA journal_mode = WAL")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self._path, timeout=5, isolation_level=None)
        try:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys = ON")
            con.execute("PRAGMA busy_timeout = 5000")
            yield con
        finally:
            con.close()


_LIST_SQL = """
SELECT v.policy_id, v.version, v.checksum, v.created_by, v.created_at,
       CASE WHEN a.policy_id IS NOT NULL THEN 1 ELSE 0 END AS active
FROM policy_versions v
LEFT JOIN policy_activation a
  ON a.singleton_id = 1 AND a.policy_id = v.policy_id AND a.version = v.version
"""


def _summary(row: sqlite3.Row) -> VersionSummary:
    return VersionSummary(
        policy_id=row["policy_id"],
        version=int(row["version"]),
        checksum=row["checksum"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        active=bool(row["active"]),
    )


def _load_stored(row: sqlite3.Row) -> PolicyDocument:
    raw = row["normalized_json"].encode("utf-8")
    if hashlib.sha256(raw).hexdigest() != row["checksum"]:
        raise PolicyStorageError()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PolicyStorageError() from exc
    report = validate_mapping(data)
    if not report.valid or report.document is None or canonical_bytes(report.document) != raw:
        raise PolicyStorageError()
    return report.document


def _encode_cursor(created_at: str, policy_id: str, version: int) -> str:
    raw = f"{created_at}|{policy_id}|{version}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(token: str) -> tuple[str, str, int]:
    if not isinstance(token, str) or not token.isascii() or len(token) > 256:
        raise InvalidCursor()
    padded = token + ("=" * (-len(token) % 4))
    try:
        text = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise InvalidCursor() from exc
    parts = text.split("|")
    if len(parts) != 3 or not _CREATED_AT.fullmatch(parts[0]) or not re.fullmatch(SLUG, parts[1]):
        raise InvalidCursor()
    if not parts[2].isdigit():
        raise InvalidCursor()
    version = int(parts[2])
    if not 1 <= version <= MAX_VERSION:
        raise InvalidCursor()
    return parts[0], parts[1], version


def _rollback(con: sqlite3.Connection) -> None:
    try:
        con.execute("ROLLBACK")
    except sqlite3.Error:
        return
