"""Exportación JSONL con manifiesto. Sin rutas controladas por el usuario."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection

from wallba.contracts.canonical import canonical_json, sha256_hex
from wallba.foundation.http import ApiError
from wallba.observability.queries import all_events, count_events, to_stored_time
from wallba.observability.schemas import MAX_EXPORT_EVENTS, ExportFilters
from wallba.observability.writer import TIME_FORMAT, verify_chain

MANIFEST_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class AuditExport:
    body: bytes
    manifest_digest: str
    count: int


def build_export(connection: Connection, filters: ExportFilters, generated_at: datetime) -> AuditExport:
    count = count_events(connection, filters)
    if count > MAX_EXPORT_EVENTS:
        raise ApiError(422, "EXPORT_TOO_LARGE", f"El rango supera {MAX_EXPORT_EVENTS} eventos")

    events = all_events(connection, filters)
    lines = [canonical_json(event.model_dump(mode="json", exclude_none=True)) for event in events]
    chain = verify_chain(connection)
    manifest = {
        "type": "manifest",
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at.strftime(TIME_FORMAT),
        "from": to_stored_time(filters.from_time),
        "to": to_stored_time(filters.to_time),
        "count": count,
        "first_sequence": events[0].sequence if events else None,
        "last_sequence": events[-1].sequence if events else None,
        "events_digest": sha256_hex(b"\n".join(lines)),
        "chain_valid": chain.valid,
        "chain_tail_hash": chain.tail_hash,
        # Guardar este digest fuera de la base es lo que da valor de ancla externa.
        "limitation": "Detecta alteraciones frente a un ancla conocida; no protege del administrador del host.",
    }
    encoded_manifest = canonical_json(manifest)
    body = b"\n".join([*lines, encoded_manifest]) + b"\n"
    return AuditExport(body=body, manifest_digest=sha256_hex(encoded_manifest), count=count)
