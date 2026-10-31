"""GET agents y POST/GET agent-runs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from wallba.agent.service import AgentRunService, get_agent, list_agents
from wallba.contracts.api import (
    AgentDetail,
    AgentRunAccepted,
    AgentRunCreate,
    AgentRunView,
    AgentSummary,
    Page,
)
from wallba.contracts.ports import Principal
from wallba.foundation.http import (
    DEFAULT_PAGE,
    MAX_PAGE,
    ApiError,
    integrations_of,
    paginate,
    require_role,
)

router = APIRouter(tags=["agents"])
Viewer = Annotated[Principal, Depends(require_role("viewer"))]
Operator = Annotated[Principal, Depends(require_role("operator", mutation=True))]


def _run_service(request: Request) -> AgentRunService:
    gateway = integrations_of(request).gateway
    if gateway is None:
        raise ApiError(503, "AUTHORIZATION_UNAVAILABLE", "Gateway no disponible")
    return AgentRunService(request.app.state.engine, gateway)


@router.get("/agents")
def agents_index(
    request: Request,
    _viewer: Viewer,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
) -> Page[AgentSummary]:
    items, next_cursor = paginate(list_agents(request.app.state.engine), lambda a: a.id, cursor, limit)
    return Page[AgentSummary](items=items, next_cursor=next_cursor)


@router.get("/agents/{agent_id}")
def agents_detail(agent_id: str, request: Request, _viewer: Viewer) -> AgentDetail:
    agent = get_agent(request.app.state.engine, agent_id)
    if agent is None:
        raise ApiError(404, "NOT_FOUND", "Agente no encontrado")
    return agent


@router.post("/agent-runs", status_code=202)
def agent_runs_create(
    body: AgentRunCreate, request: Request, background: BackgroundTasks, operator: Operator
) -> AgentRunAccepted:
    if not request.app.state.settings.demo_enabled:
        raise ApiError(403, "DEMO_DISABLED", "Solo disponible en el perfil demo")
    service = _run_service(request)
    accepted = service.create(body.scenario_id, operator)
    background.add_task(service.execute, accepted.run_id, body.scenario_id, 0, operator)
    return accepted


@router.get("/agent-runs/{run_id}")
def agent_runs_detail(run_id: str, request: Request, _viewer: Viewer) -> AgentRunView:
    view = _run_service(request).view(run_id)
    if view is None:
        raise ApiError(404, "NOT_FOUND", "Run no encontrado")
    return view
