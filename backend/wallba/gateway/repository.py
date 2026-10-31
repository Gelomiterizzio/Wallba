"""Persona 3 transaction helpers. Returned views use P1's public DTOs."""

import json
from datetime import UTC, datetime

from sqlalchemy import select, update

from wallba.approvals.models import approvals
from wallba.contracts.canonical import CanonicalRequest
from wallba.contracts.decision import DecisionEnvelope, ExecutionReceipt, RequestView
from wallba.foundation.http import ApiError
from wallba.gateway.schema import executions, requests


def utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Reloj sin zona horaria")
    return value.astimezone(UTC)


def stamp(value):
    return utc(value).isoformat(timespec="microseconds")


def instant(value):
    return utc(datetime.fromisoformat(value))


def request_row(connection, request_id):
    return (
        connection.execute(select(requests).where(requests.c.request_id == request_id))
        .mappings()
        .first()
    )


def canonical_from(row):
    try:
        canonical = CanonicalRequest.model_validate(row["canonical_json"])
        if (
            canonical.digest() != row["request_digest"]
            or canonical.call.request_id != row["request_id"]
            or canonical.principal_id != row["principal_id"]
            or canonical.call.agent_id != row["agent_id"]
        ):
            raise ValueError()
        return canonical
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ApiError(
            409, "DIGEST_MISMATCH", "La solicitud guardada no coincide con su snapshot"
        ) from exc


def view_of(connection, row):
    approval = connection.execute(
        select(approvals.c.approval_id).where(
            approvals.c.request_id == row["request_id"]
        )
    ).scalar_one_or_none()
    execution = (
        connection.execute(
            select(executions).where(executions.c.request_id == row["request_id"])
        )
        .mappings()
        .first()
    )
    return RequestView(
        request_id=row["request_id"],
        state=row["state"],
        decision=DecisionEnvelope.model_validate(row["decision_json"])
        if row["decision_json"]
        else None,
        approval_id=approval,
        execution_id=execution["execution_id"] if execution else None,
        receipt=ExecutionReceipt.model_validate_json(
            json.dumps(execution["receipt_json"])
        )
        if execution and execution["receipt_json"]
        else None,
    )


def set_state(connection, request_id, state):
    connection.execute(
        update(requests)
        .where(requests.c.request_id == request_id)
        .values(
            state=state,
            row_version=requests.c.row_version + 1,
        )
    )
