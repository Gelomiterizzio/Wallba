"""API de catálogo, demo-runs, evidencia y matriz."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from wallba.contracts.api import (
    DemoRunAccepted,
    DemoRunCreate,
    DemoRunView,
    EvidenceView,
    MatrixRow,
    Page,
    ScenarioId,
    ScenarioView,
)
from wallba.contracts.ports import Principal
from wallba.demo.runner import AuditUnavailable, DemoConflict, PairedRunner
from wallba.demo.scenarios import SCENARIOS
from wallba.foundation.http import DEFAULT_PAGE, MAX_PAGE, ApiError, integrations_of, paginate, require_role

router = APIRouter(tags=["demo"])
Viewer = Annotated[Principal, Depends(require_role("viewer"))]
Operator = Annotated[Principal, Depends(require_role("operator", mutation=True))]


def _runner(request: Request) -> PairedRunner:
    runner_factory = request.app.state.runner_factory
    runner = runner_factory(integrations_of(request))
    if runner is None:
        raise ApiError(503, "DEMO_UNAVAILABLE", "Demo no disponible: faltan gateway, auditoría o ejecutores")
    return runner


@router.get("/scenarios")
def scenarios_index(
    _viewer: Viewer,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
) -> Page[ScenarioView]:
    ordered = sorted((scenario.view() for scenario in SCENARIOS), key=lambda s: s.id, reverse=True)
    items, next_cursor = paginate(ordered, lambda s: s.id, cursor, limit)
    return Page[ScenarioView](items=items, next_cursor=next_cursor)


@router.post("/demo-runs", status_code=202)
def demo_runs_create(
    body: DemoRunCreate, request: Request, background: BackgroundTasks, operator: Operator
) -> DemoRunAccepted:
    if not request.app.state.settings.demo_enabled:
        raise ApiError(403, "DEMO_DISABLED", "Solo disponible en el perfil demo")
    runner = _runner(request)
    try:
        accepted = runner.start(body.scenario_id, body.seed, operator)
    except DemoConflict as exc:
        raise ApiError(409, "DEMO_ALREADY_ACTIVE", "Ya existe un run activo") from exc
    except AuditUnavailable as exc:
        raise ApiError(503, "AUDIT_UNAVAILABLE", "Auditoría no disponible") from exc
    background.add_task(runner.execute, accepted.run_id, operator)
    return accepted


@router.get("/demo-runs/{run_id}")
def demo_runs_detail(run_id: str, request: Request, viewer: Viewer) -> DemoRunView:
    runner = _runner(request)
    try:
        runner.refresh(run_id, viewer)
    except KeyError as exc:
        raise ApiError(404, "NOT_FOUND", "Run no encontrado") from exc
    view = runner.view(run_id)
    if view is None:
        raise ApiError(404, "NOT_FOUND", "Run no encontrado")
    return view


@router.get("/demo-runs/{run_id}/evidence")
def demo_runs_evidence(run_id: str, request: Request, _viewer: Viewer) -> EvidenceView:
    evidence = _runner(request).evidence(run_id)
    if evidence is None:
        raise ApiError(404, "NOT_FOUND", "Evidencia no encontrada")
    return evidence


@router.get("/matrix")
def matrix(
    request: Request,
    _viewer: Viewer,
    scenario_id: ScenarioId | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
) -> Page[MatrixRow]:
    rows = _runner(request).matrix(scenario_id)
    key = lambda row: f"{row.observed_at.isoformat()}|{row.run_id}"  # noqa: E731
    items, next_cursor = paginate(rows, key, cursor, limit)
    return Page[MatrixRow](items=items, next_cursor=next_cursor)
