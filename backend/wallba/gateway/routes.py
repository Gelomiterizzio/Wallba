"""Persona 3 HTTP boundary; mounted through P1's extra_routers hook."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from wallba.auth.tokens import hash_opaque_token
from wallba.contracts.ports import Principal
from wallba.foundation.http import ApiError
from wallba.gateway.normalization import parse_call


async def bounded_body(request):
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Se requiere JSON")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise ApiError(413, "PAYLOAD_TOO_LARGE", "La solicitud supera el límite")
    return bytes(body)


def caller(request, authorizer, *, mutation=False):
    if request.headers.getlist("authorization"):
        agent = authorizer.require_agent(request)
        raw = request.headers["authorization"].partition(" ")[2]
        return (
            Principal(principal_id=agent.principal_id, kind="agent", roles=[]),
            hash_opaque_token(raw),
            agent,
        )
    principal = (
        authorizer.require(request, "operator", mutation=True)
        if mutation
        else authorizer.authenticate(request)
    )
    return principal, None, None


def build_router(gateway, authorizer):
    router = APIRouter(tags=["Persona 3 — Gateway"])

    @router.post("/tool-requests")
    async def submit(request: Request):
        principal, credential_hash, agent = caller(request, authorizer, mutation=True)
        call = parse_call(await bounded_body(request))
        if agent is not None:
            if agent.agent_id != call.agent_id:
                raise ApiError(
                    403, "SCOPE_DENIED", "El agente no corresponde a la credencial"
                )
            authorizer.require_agent_scope(request, call.tool, call.resource_id)
        if len(request.headers.getlist("idempotency-key")) != 1:
            raise ApiError(
                422, "VALIDATION_ERROR", "Se requiere una única Idempotency-Key"
            )
        from starlette.concurrency import run_in_threadpool

        view = await run_in_threadpool(
            gateway.submit,
            call,
            principal,
            request.headers["idempotency-key"],
            credential_hash=credential_hash,
        )
        status = 202 if view.state in {"PENDING_APPROVAL", "EXECUTING"} else 200
        if view.state == "DENIED":
            code = view.decision.reason_code
            raise ApiError(
                503
                if code
                in {"POLICY_MISSING", "POLICY_INVALID", "AUTHORIZATION_UNAVAILABLE"}
                else 403,
                code,
                "Operación bloqueada por WALLBA",
            )
        return JSONResponse(
            view.model_dump(mode="json"),
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/tool-requests/{request_id}")
    def get(request_id: str, request: Request):
        principal, _, _ = caller(request, authorizer)
        return gateway.get(request_id, principal)

    @router.get("/tool-requests/{request_id}/events")
    def events(request_id: str, request: Request):
        principal, _, _ = caller(request, authorizer)
        return {
            "items": gateway.request_events(request_id, principal),
            "source": "PERSONA_3_TRANSACTIONAL_OUTBOX",
        }

    @router.post("/tool-requests/{request_id}/reconcile")
    def reconcile(request_id: str, request: Request):
        principal = authorizer.require(request, "operator", mutation=True)
        gateway.get(request_id, principal)
        gateway.reconcile(request_id)
        return gateway.get(request_id, principal)

    return router
