"""P3 transactional outbox, not a substitute for P4's global audit dashboard."""

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import insert

from wallba.gateway.schema import events

SAFE_FIELDS = frozenset(
    {
        "event_type",
        "request_id",
        "run_id",
        "principal_id",
        "actor_id",
        "execution_id",
        "approval_id",
        "evidence_id",
        "request_digest",
        "decision",
        "risk",
        "policy_id",
        "policy_version",
        "reason_code",
        "matched_rule_ids",
        "state",
        "status",
        "checksum",
        "occurred_at",
    }
)


class TransactionalOutbox:
    """Stores evidence inside the producer's SQLAlchemy or sqlite3 transaction.

    P1/P2 event formats are adapted without changing either module. P4 can
    consume this outbox later. No logs contain tool arguments or credentials.
    """

    def append(self, event, transaction):
        if hasattr(event, "model_dump"):
            event = event.model_dump(mode="json")
        if not isinstance(event, Mapping) or not event.get("event_type"):
            raise ValueError("Evento de auditoría inválido")
        payload = {key: value for key, value in event.items() if key in SAFE_FIELDS}
        row = {
            "event_id": str(uuid4()),
            "event_type": payload["event_type"],
            "request_id": payload.get("request_id"),
            "run_id": payload.get("run_id"),
            "principal_id": payload.get("principal_id", payload.get("actor_id")),
            "occurred_at": payload.get("occurred_at")
            or datetime.now(UTC).isoformat(),
            "payload_json": payload,
        }
        if hasattr(transaction, "exec_driver_sql"):
            transaction.execute(insert(events).values(**row))
        else:
            import json

            transaction.execute(
                "INSERT INTO p3_audit_outbox (event_id,event_type,request_id,run_id,principal_id,occurred_at,payload_json) "
                "VALUES (:event_id,:event_type,:request_id,:run_id,:principal_id,:occurred_at,:payload_json)",
                {
                    **row,
                    "payload_json": json.dumps(
                        payload, sort_keys=True, separators=(",", ":")
                    ),
                },
            )
        _mirror_dashboard(payload, transaction)
        return row["event_id"]


def _mirror_dashboard(payload, transaction) -> None:
    """Copia el evento a la cadena que lee el dashboard. Un campo inválido no borra el outbox."""
    from wallba.observability.ports import AuditSchemaError, AuditWriteError
    from wallba.observability.writer import AuditWriter

    plain = {}
    for key, value in payload.items():
        if value is None:
            continue
        plain[key] = value.value if isinstance(value, Enum) else value
    try:
        AuditWriter().append(plain, transaction)
    except (AuditSchemaError, AuditWriteError, ValueError, TypeError):
        return
