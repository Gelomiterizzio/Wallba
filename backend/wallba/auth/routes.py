"""HTTP adapter: real routes mounted in the shared FastAPI application."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from wallba.auth.http_handlers import handle_login, handle_logout, handle_me
from wallba.auth.models import Role


class LoginInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(
        min_length=1, max_length=1024, repr=False, json_schema_extra={"writeOnly": True}
    )


class LoginOutput(BaseModel):
    csrf_token: str = Field(repr=False)
    roles: list[Role]


class IdentityOutput(LoginOutput):
    principal_id: str
    username: str
    kind: Literal["human"]


def error(status, code, request_id, details=()):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": "La solicitud no es válida.",
                "request_id": request_id,
                "details": list(details),
            }
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def build_router(service):
    router = APIRouter(prefix="/auth", tags=["Persona 3 — authentication"])

    def render(result):
        response = (
            Response(status_code=204)
            if result.status_code == 204
            else JSONResponse(result.body, status_code=result.status_code)
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        if result.status_code == 429:
            response.headers["Retry-After"] = "300"
        if result.set_cookie:
            cookie = result.set_cookie
            response.set_cookie(
                cookie.name,
                cookie.value,
                max_age=cookie.max_age,
                path=cookie.path,
                secure=cookie.secure,
                httponly=cookie.http_only,
                samesite=cookie.same_site,
            )
        if result.clear_cookie:
            settings = service.settings
            response.delete_cookie(
                settings.cookie_name,
                path=settings.cookie_path,
                secure=settings.cookie_secure,
                httponly=True,
                samesite="strict",
            )
        return response

    @router.post(
        "/login",
        response_model=LoginOutput,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": LoginInput.model_json_schema()}
                },
            }
        },
    )
    async def login(request: Request):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            return error(415, "UNSUPPORTED_MEDIA_TYPE", request_id)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                return error(413, "PAYLOAD_TOO_LARGE", request_id)
        # Peer is server-derived. Never trust X-Forwarded-For from the client.
        peer = request.client.host if request.client else "unknown-peer"
        result = await run_in_threadpool(
            handle_login,
            service,
            bytes(body),
            request.headers.get("origin"),
            peer,
            request_id,
        )
        return render(result)

    @router.get("/me", response_model=IdentityOutput)
    async def me(request: Request):
        result = await run_in_threadpool(
            handle_me,
            service,
            request.headers.get("cookie"),
            getattr(request.state, "request_id", str(uuid4())),
        )
        return render(result)

    @router.post("/logout", status_code=204)
    async def logout(request: Request):
        result = await run_in_threadpool(
            handle_logout,
            service,
            request.headers.get("cookie"),
            request.headers.get("x-csrf-token"),
            request.headers.get("origin"),
            getattr(request.state, "request_id", str(uuid4())),
        )
        return render(result)

    return router
