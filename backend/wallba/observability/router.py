"""GET /dashboard y /audit*. El RBAC lo resuelve el autorizador de P3."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from wallba.contracts.ports import Principal
from wallba.foundation.clock import utc_now
from wallba.foundation.http import ApiError, require_role
from wallba.observability.exports import build_export
from wallba.observability.queries import dashboard, get_event, list_events
from wallba.observability.schemas import (
    AuditEventDetail,
    AuditEventPage,
    AuditQuery,
    DashboardQuery,
    DashboardView,
    ExportQuery,
    IntegrityView,
)
from wallba.observability.writer import verify_chain

router = APIRouter(tags=["observability"])
Viewer = Annotated[Principal, Depends(require_role("viewer"))]
CHAIN_LIMITATION = (
    "Detecta alteraciones de eventos frente a la cadena; quien administra el host puede reescribirla completa."
)


@router.get("/dashboard")
def dashboard_view(filters: DashboardQuery, request: Request, _viewer: Viewer) -> DashboardView:
    with request.app.state.engine.connect() as connection:
        return dashboard(connection, filters, utc_now())


@router.get("/audit")
def audit_index(filters: AuditQuery, request: Request, _viewer: Viewer) -> AuditEventPage:
    with request.app.state.engine.connect() as connection:
        return list_events(connection, filters)


# Debe declararse antes de /audit/{event_id}.
@router.get("/audit/export", response_class=Response)
def audit_export(filters: ExportQuery, request: Request, _viewer: Viewer) -> Response:
    with request.app.state.engine.connect() as connection:
        export = build_export(connection, filters, utc_now())
    return Response(
        content=export.body,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": 'attachment; filename="wallba-audit.jsonl"',
            "X-Wallba-Manifest-Digest": export.manifest_digest,
            "X-Wallba-Event-Count": str(export.count),
        },
    )


@router.get("/audit/{event_id}")
def audit_detail(event_id: str, request: Request, _viewer: Viewer) -> AuditEventDetail:
    with request.app.state.engine.connect() as connection:
        event = get_event(connection, event_id)
        if event is None:
            raise ApiError(404, "NOT_FOUND", "Evento no encontrado")
        chain = verify_chain(connection, through_sequence=event.sequence)
    return AuditEventDetail(
        event=event,
        integrity=IntegrityView(
            verified=chain.valid,
            checked_events=chain.checked,
            first_invalid_sequence=chain.first_invalid_sequence,
            limitation=CHAIN_LIMITATION,
        ),
    )
