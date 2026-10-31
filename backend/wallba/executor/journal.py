"""Journal duradero: execution_id y nonce únicos, y receipt recuperable."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text

from wallba.contracts.canonical import canonical_json, sha256_hex
from wallba.contracts.decision import ExecutionReceipt
from wallba.contracts.results import TOOL_RESULT_ADAPTER, ToolResult


@dataclass(frozen=True)
class JournalEntry:
    nonce_hash: str
    request_digest: str
    receipt: ExecutionReceipt
    result: ToolResult | None


def _row_to_entry(row) -> JournalEntry:
    result = TOOL_RESULT_ADAPTER.validate_json(row.result_json) if row.result_json else None
    completed_at = datetime.fromisoformat(row.completed_at) if row.completed_at else None
    receipt = ExecutionReceipt(
        execution_id=row.execution_id,
        request_id=row.request_id,
        state=row.state,
        result_digest=row.result_digest,
        effect_count=row.effect_count,
        evidence_id=row.evidence_id,
        completed_at=completed_at,
    )
    return JournalEntry(
        nonce_hash=row.nonce_hash,
        request_digest=row.request_digest,
        receipt=receipt,
        result=result,
    )


_SELECT = (
    "SELECT execution_id, nonce_hash, request_id, request_digest, state, result_digest, "
    "result_json, effect_count, evidence_id, completed_at FROM execution_journal "
)


def find_by_execution(connection: Connection, execution_id: str) -> JournalEntry | None:
    row = connection.execute(
        text(_SELECT + "WHERE execution_id = :execution_id"), {"execution_id": execution_id}
    ).first()
    return _row_to_entry(row) if row else None


def nonce_exists(connection: Connection, nonce_hash: str) -> bool:
    row = connection.execute(
        text("SELECT 1 FROM execution_journal WHERE nonce_hash = :nonce_hash"),
        {"nonce_hash": nonce_hash},
    ).first()
    return row is not None


def record(
    connection: Connection,
    *,
    execution_id: str,
    nonce_hash: str,
    request_id: str,
    request_digest: str,
    state: str,
    result: ToolResult | None,
    effect_count: int | None,
    completed_at: datetime,
) -> ExecutionReceipt:
    """Inserta claim y receipt en la transacción del efecto; UNIQUE impide el doble claim."""
    result_data = TOOL_RESULT_ADAPTER.dump_python(result, mode="json") if result is not None else None
    result_digest = sha256_hex(canonical_json(result_data)) if result_data is not None else None
    receipt = ExecutionReceipt(
        execution_id=execution_id,
        request_id=request_id,
        state=state,
        result_digest=result_digest,
        effect_count=effect_count,
        evidence_id=str(uuid.uuid4()),
        completed_at=completed_at,
    )
    connection.execute(
        text(
            "INSERT INTO execution_journal (execution_id, nonce_hash, request_id, request_digest, "
            "state, result_digest, result_json, effect_count, evidence_id, completed_at) VALUES "
            "(:execution_id, :nonce_hash, :request_id, :request_digest, :state, :result_digest, "
            ":result_json, :effect_count, :evidence_id, :completed_at)"
        ),
        {
            "execution_id": execution_id,
            "nonce_hash": nonce_hash,
            "request_id": request_id,
            "request_digest": request_digest,
            "state": state,
            "result_digest": result_digest,
            "result_json": json.dumps(result_data, ensure_ascii=False) if result_data is not None else None,
            "effect_count": effect_count,
            "evidence_id": receipt.evidence_id,
            "completed_at": completed_at.isoformat(),
        },
    )
    return receipt
