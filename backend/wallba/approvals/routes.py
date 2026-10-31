from fastapi import APIRouter, Request
from pydantic import Field, ValidationError

from wallba.auth.http_handlers import _read_cookie
from wallba.auth.tokens import hash_opaque_token
from wallba.contracts.canonical import loads_strict
from wallba.contracts.common import StrictModel
from wallba.foundation.http import ApiError
from wallba.gateway.routes import bounded_body


class ActionBody(StrictModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


def build_router(service, authorizer):
    router = APIRouter(prefix="/approvals", tags=["Persona 3 — Aprobaciones"])

    @router.get("")
    def listing(request: Request):
        actor = authorizer.require(request, "viewer", mutation=False)
        query = request.query_params
        if any(
            key not in {"status", "agent_id", "risk", "cursor", "limit"}
            or len(query.getlist(key)) != 1
            for key in query
        ):
            raise ApiError(422, "VALIDATION_ERROR", "Filtros no válidos")
        limit = query.get("limit", "50")
        if not limit.isascii() or not limit.isdecimal() or len(limit) > 3:
            raise ApiError(422, "VALIDATION_ERROR", "Límite no válido")
        return service.list(
            actor,
            status=query.get("status"),
            agent_id=query.get("agent_id"),
            risk=query.get("risk"),
            cursor=query.get("cursor"),
            limit=int(limit),
        )

    @router.get("/{approval_id}")
    def detail(approval_id: str, request: Request):
        return service.get(
            approval_id, authorizer.require(request, "viewer", mutation=False)
        )

    async def act(approval_id, action, request):
        actor = authorizer.authenticate(request)
        authorizer.require_csrf(request)
        try:
            body = ActionBody.model_validate(loads_strict(await bounded_body(request)))
        except (
            ValidationError,
            ValueError,
            TypeError,
            UnicodeError,
            RecursionError,
        ) as exc:
            raise ApiError(422, "VALIDATION_ERROR", "Acción no válida") from exc
        raw_session = _read_cookie(
            request.headers.get("cookie"), authorizer.service.settings.cookie_name
        )
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(
            service.resolve,
            approval_id,
            actor,
            action,
            body.expected_version,
            body.reason,
            session_hash=hash_opaque_token(raw_session),
        )

    @router.post("/{approval_id}/approve")
    async def approve(approval_id: str, request: Request):
        return await act(approval_id, "approve", request)

    @router.post("/{approval_id}/reject")
    async def reject(approval_id: str, request: Request):
        return await act(approval_id, "reject", request)

    @router.post("/{approval_id}/cancel")
    async def cancel(approval_id: str, request: Request):
        return await act(approval_id, "cancel", request)

    return router
