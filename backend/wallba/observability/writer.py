"""AuditWriter: secuencia y hash encadenado dentro de la transacción del productor.

Recibe la conexión abierta por quien produce el evento (SQLAlchemy o sqlite3), de modo
que el evento y la transición crítica se confirman o se revierten juntos. El productor
debe haber abierto BEGIN IMMEDIATE; si no, el UNIQUE de sequence rechaza la carrera.

La cadena detecta alteraciones frente a un ancla conocida. Quien administra el host
puede reescribir la base y la cadena completas: esto no protege contra él.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Connection

from wallba.contracts.canonical import canonical_json, sha256_hex
from wallba.foundation.clock import utc_now
from wallba.observability.ports import AuditWriteError
from wallba.observability.redaction import safe_event_fields

SCHEMA_VERSION = "1"
GENESIS_HASH = "0" * 64
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_FILTER_COLUMNS = (
    "request_id",
    "run_id",
    "execution_id",
    "principal_id",
    "agent_id",
    "environment_id",
    "tool",
    "decision",
    "risk",
    "reason_code",
)
_INSERT = (
    "INSERT INTO audit_events (event_id, sequence, event_type, occurred_at, "
    + ", ".join(_FILTER_COLUMNS)
    + ", fields_json, previous_hash, event_hash) VALUES ("
    + ", ".join("?" * (len(_FILTER_COLUMNS) + 7))
    + ")"
)
_TAIL = "SELECT sequence, event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"


def _run(transaction: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    """Ambos drivers aceptan parámetros `?`; SQLAlchemy los pasa directos al de SQLite."""
    if isinstance(transaction, Connection):
        return transaction.exec_driver_sql(sql, params)
    if isinstance(transaction, sqlite3.Connection):
        return transaction.execute(sql, params)
    raise AuditWriteError("tipo de transacción no soportado")


class AuditWriter:
    """Implementa AuditSink."""

    def __init__(self, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock

    def append(self, event: BaseModel | Mapping[str, Any], transaction: Any) -> str:
        draft = event.model_dump() if isinstance(event, BaseModel) else event
        fields = safe_event_fields(draft)
        tail = _run(transaction, _TAIL).fetchone()
        sequence = tail[0] + 1 if tail else 1
        previous_hash = tail[1] if tail else GENESIS_HASH
        event_id = str(uuid.uuid4())
        payload = {
            **fields,
            "schema_version": SCHEMA_VERSION,
            "event_id": event_id,
            "sequence": sequence,
            "occurred_at": self._clock().strftime(TIME_FORMAT),
            "previous_hash": previous_hash,
        }
        encoded = canonical_json(payload)
        _run(
            transaction,
            _INSERT,
            (
                event_id,
                sequence,
                payload["event_type"],
                payload["occurred_at"],
                *(fields.get(column) for column in _FILTER_COLUMNS),
                encoded.decode("utf-8"),
                previous_hash,
                sha256_hex(encoded),
            ),
        )
        return event_id


@dataclass(frozen=True)
class ChainReport:
    valid: bool
    checked: int
    first_invalid_sequence: int | None
    tail_hash: str


def verify_chain(connection: Any, through_sequence: int | None = None) -> ChainReport:
    """Recalcula la cadena desde el origen, incluidas las columnas usadas para filtrar."""
    columns = ("event_id", "sequence", "event_type", "occurred_at", *_FILTER_COLUMNS)
    sql = (
        f"SELECT {', '.join(columns)}, fields_json, previous_hash, event_hash "
        "FROM audit_events ORDER BY sequence"
    )
    previous = GENESIS_HASH
    checked = 0
    for row in _run(connection, sql).fetchall():
        sequence = row[1]
        if through_sequence is not None and sequence > through_sequence:
            break
        if not _row_is_valid(row, columns, checked + 1, previous):
            return ChainReport(False, checked, sequence, previous)
        previous = row[-1]
        checked += 1
    return ChainReport(True, checked, None, previous)


def _row_is_valid(row: Any, columns: tuple[str, ...], expected: int, previous: str) -> bool:
    fields_json, previous_hash, event_hash = row[-3], row[-2], row[-1]
    if row[1] != expected or previous_hash != previous:
        return False
    if sha256_hex(fields_json.encode("utf-8")) != event_hash:
        return False
    payload = json.loads(fields_json)
    # Alterar una columna de filtro dejaría el JSON intacto: también se compara.
    return all(payload.get(name) == row[index] for index, name in enumerate(columns))
