"""Consultas parametrizadas compuestas solo a partir de campos permitidos."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Connection, text

from wallba.contracts.common import UUID_PATTERN
from wallba.foundation.http import ApiError, decode_cursor, encode_cursor
from wallba.observability.schemas import (
    AuditEventPage,
    AuditEventView,
    AuditFilters,
    DashboardCounters,
    DashboardFilters,
    DashboardView,
    DecisionCounts,
    RiskCounts,
)
from wallba.observability.writer import TIME_FORMAT

_EXACT_FILTERS = ("tool", "agent_id", "decision", "risk", "event_type", "request_id", "run_id")
_SEARCH_COLUMNS = ("event_id", "request_id", "run_id", "execution_id", "principal_id", "agent_id", "reason_code")
_SELECT = "SELECT fields_json, previous_hash, event_hash FROM audit_events"
BASELINE_ENVIRONMENT = "baseline-fixture"
RECENT_EVENTS = 10
_RESOLVED_APPROVALS = (
    "approval_approved",
    "approval_rejected",
    "approval_expired",
    "approval_cancelled",
)


def to_stored_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(TIME_FORMAT)


def _row_to_view(row: Any) -> AuditEventView:
    payload = json.loads(row.fields_json)
    return AuditEventView.model_validate_json(
        json.dumps({**payload, "event_hash": row.event_hash, "previous_hash": row.previous_hash})
    )


def _where(filters: AuditFilters) -> tuple[list[str], dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for name in _EXACT_FILTERS:
        value = getattr(filters, name)
        if value is not None:
            clauses.append(f"{name} = :{name}")
            params[name] = value
    if filters.q is not None:
        # Búsqueda exacta por identificadores y códigos: no recorre contenido.
        clauses.append("(" + " OR ".join(f"{column} = :q" for column in _SEARCH_COLUMNS) + ")")
        params["q"] = filters.q
    clauses.extend(_time_clauses(filters.from_time, filters.to_time, params))
    return clauses, params


def _time_clauses(start: datetime | None, end: datetime | None, params: dict[str, Any]) -> list[str]:
    clauses = []
    if start is not None:
        clauses.append("occurred_at >= :from_time")
        params["from_time"] = to_stored_time(start)
    if end is not None:
        clauses.append("occurred_at < :to_time")
        params["to_time"] = to_stored_time(end)
    return clauses


def _sql_where(clauses: list[str]) -> str:
    return " WHERE " + " AND ".join(clauses) if clauses else ""


def _parse_cursor(cursor: str) -> int:
    decoded = decode_cursor(cursor)
    if not decoded.isdigit():
        raise ApiError(422, "VALIDATION_ERROR", "Cursor inválido")
    return int(decoded)


def list_events(connection: Connection, filters: AuditFilters) -> AuditEventPage:
    """Pagina por sequence: los eventos nuevos no desplazan las páginas ya leídas."""
    clauses, params = _where(filters)
    if filters.cursor is not None:
        clauses.append("sequence < :before")
        params["before"] = _parse_cursor(filters.cursor)
    params["fetch"] = filters.limit + 1
    rows = connection.execute(
        text(f"{_SELECT}{_sql_where(clauses)} ORDER BY sequence DESC LIMIT :fetch"), params
    ).all()
    items = [_row_to_view(row) for row in rows[: filters.limit]]
    has_more = len(rows) > filters.limit
    return AuditEventPage(
        items=items, next_cursor=encode_cursor(str(items[-1].sequence)) if has_more else None
    )


def get_event(connection: Connection, event_id: str) -> AuditEventView | None:
    if not re.fullmatch(UUID_PATTERN, event_id):
        raise ApiError(422, "VALIDATION_ERROR", "Identificador inválido")
    row = connection.execute(text(f"{_SELECT} WHERE event_id = :id"), {"id": event_id}).first()
    return _row_to_view(row) if row else None


def count_events(connection: Connection, filters: AuditFilters) -> int:
    clauses, params = _where(filters)
    return connection.execute(
        text(f"SELECT COUNT(*) FROM audit_events{_sql_where(clauses)}"), params
    ).scalar_one()


def all_events(connection: Connection, filters: AuditFilters) -> list[AuditEventView]:
    clauses, params = _where(filters)
    rows = connection.execute(text(f"{_SELECT}{_sql_where(clauses)} ORDER BY sequence"), params).all()
    return [_row_to_view(row) for row in rows]


def dashboard(connection: Connection, filters: DashboardFilters, as_of: datetime) -> DashboardView:
    """Todo sale de una misma lectura, sobre eventos persistidos."""
    params: dict[str, Any] = {}
    clauses = _time_clauses(filters.from_time, filters.to_time, params)
    if not filters.include_baseline:
        # IS NOT: los eventos sin entorno (demo_started, policy_activated) no son baseline.
        clauses.append("environment_id IS NOT :baseline")
        params["baseline"] = BASELINE_ENVIRONMENT
    where = _sql_where(clauses)

    by_type = dict(
        connection.execute(
            text(f"SELECT event_type, COUNT(*) FROM audit_events{where} GROUP BY event_type"), params
        ).all()
    )
    decided = _sql_where([*clauses, "event_type = 'authorization_decided'"])
    by_decision = dict(
        connection.execute(
            text(f"SELECT decision, COUNT(*) FROM audit_events{decided} AND decision IS NOT NULL GROUP BY decision"),
            params,
        ).all()
    )
    by_risk = dict(
        connection.execute(
            text(f"SELECT risk, COUNT(*) FROM audit_events{decided} AND risk IS NOT NULL GROUP BY risk"), params
        ).all()
    )
    recent = connection.execute(
        text(f"{_SELECT}{where} ORDER BY sequence DESC LIMIT {RECENT_EVENTS}"), params
    ).all()

    resolved = sum(by_type.get(name, 0) for name in _RESOLVED_APPROVALS)
    counters = DashboardCounters(
        events=sum(by_type.values()),
        requests=by_type.get("request_received", 0),
        decisions=by_type.get("authorization_decided", 0),
        executions_completed=by_type.get("execution_completed", 0),
        executions_failed=by_type.get("execution_failed", 0),
        executions_unknown=by_type.get("execution_unknown", 0),
        approvals_pending=max(by_type.get("approval_created", 0) - resolved, 0),
    )
    return DashboardView(
        as_of=as_of,
        window_from=filters.from_time.astimezone(timezone.utc) if filters.from_time else None,
        window_to=filters.to_time.astimezone(timezone.utc) if filters.to_time else None,
        include_baseline=filters.include_baseline,
        counters=counters,
        by_decision=DecisionCounts(**by_decision),
        by_risk=RiskCounts(**by_risk),
        recent=[_row_to_view(row) for row in recent],
    )
