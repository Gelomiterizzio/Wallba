"""Rutas administrativas de políticas. La sesión, el rol y el CSRF los resuelve Persona 3."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from wallba.policy.schemas import MAX_DOCUMENT_BYTES
from wallba.policy.service import (
    InvalidCursor,
    InvalidPolicy,
    PolicyConflict,
    PolicyNotFound,
    PolicyService,
    PolicyUnavailable,
)

MAX_HTTP_BODY = 96 * 1024
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LIMIT = re.compile(r"^[1-9][0-9]*$")

_MESSAGES = {
    "UNAUTHENTICATED": "Se requiere una sesión.",
    "FORBIDDEN": "Permiso insuficiente para esta operación.",
    "NOT_FOUND": "La versión de política no existe.",
    "STALE_POLICY": "La versión activa cambió. Vuelve a leerla antes de reintentar.",
    "CONFLICT": "Esa versión ya existe y no se puede modificar.",
    "POLICY_INVALID": "La política no supera la validación.",
    "VALIDATION_ERROR": "La solicitud no es válida.",
    "AUDIT_UNAVAILABLE": "No se pudo registrar la auditoría obligatoria.",
    "AUTHORIZATION_UNAVAILABLE": "El servicio de políticas no está disponible.",
}


@dataclass(frozen=True)
class PolicyActor:
    """Vista mínima que el gateway de Persona 3 debe rellenar. No es una sesión."""

    principal_id: str
    kind: str
    roles: frozenset[str]
    csrf_valid: bool


class PolicyHttpError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        details: list[dict[str, str]] | None = None,
        request_id: str | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.details = details or []
        self.request_id = request_id
        super().__init__(code)


class ValidateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format: Literal["yaml", "json"]
    content: str = Field(strict=True)


class ActivateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(strict=True, ge=1, le=1_000_000)
    expected_active_version: int | None = Field(strict=True)


def mount_policy_api(
    app: FastAPI,
    service: PolicyService,
    actor_provider: Callable[[], PolicyActor | None],
) -> None:
    app.include_router(create_policy_router(service, actor_provider), prefix="/api/v1")
    register_policy_exception_handlers(app)


def create_policy_router(service: PolicyService, actor_provider: Callable[[], PolicyActor | None]):
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/policies")
    async def list_policies(request: Request) -> JSONResponse:
        request_id = _request_id()
        _viewer(actor_provider(), request_id)
        limit, cursor = _list_query(request.query_params, request_id)
        try:
            page = service.list_versions(cursor, limit)
        except InvalidCursor as exc:
            raise PolicyHttpError(
                422,
                "VALIDATION_ERROR",
                [{"field": "cursor", "code": "invalid_value"}],
                request_id,
            ) from exc
        except PolicyUnavailable as exc:
            raise PolicyHttpError(503, exc.code, request_id=request_id) from exc
        return _json(
            {"items": [_summary(item) for item in page.items], "next_cursor": page.next_cursor},
            request_id,
        )

    @router.get("/policies/{policy_id}/versions/{version}")
    async def get_version(policy_id: str, version: str) -> JSONResponse:
        request_id = _request_id()
        _viewer(actor_provider(), request_id)
        version_number = _version(version, request_id)
        _policy_id(policy_id, request_id)
        try:
            found = service.get_version(policy_id, version_number)
        except PolicyNotFound as exc:
            raise PolicyHttpError(404, "NOT_FOUND", request_id=request_id) from exc
        except PolicyUnavailable as exc:
            raise PolicyHttpError(503, exc.code, request_id=request_id) from exc
        except InvalidPolicy as exc:
            raise PolicyHttpError(422, "VALIDATION_ERROR", _details(exc.errors), request_id) from exc
        body = _summary(found.summary)
        body["document"] = found.document.model_dump(mode="json", by_alias=True, exclude_none=True)
        return _json(body, request_id)

    @router.post("/policies/validate")
    async def validate_policy(request: Request) -> JSONResponse:
        request_id = _request_id()
        _admin(actor_provider(), request_id)
        raw = await _body(request, request_id)
        payload = _object(raw, request_id)
        try:
            body = ValidateBody.model_validate(payload)
        except ValidationError as exc:
            raise PolicyHttpError(422, "VALIDATION_ERROR", _pydantic_details(exc), request_id) from exc
        encoded = body.content.encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise PolicyHttpError(413, "POLICY_INVALID", [{"field": "content", "code": "max_bytes"}], request_id)
        report = service.validate_content(body.content, body.format)
        if not report.valid:
            raise PolicyHttpError(422, "POLICY_INVALID", _details(report.errors), request_id)
        return _json(
            {"valid": True, "errors": [], "normalized_policy": report.normalized_policy()},
            request_id,
        )

    @router.post("/policies/{policy_id}/versions", status_code=201)
    async def create_version(policy_id: str, request: Request) -> JSONResponse:
        request_id = _request_id()
        actor = _admin(actor_provider(), request_id)
        _policy_id(policy_id, request_id)
        raw = await _body(request, request_id)
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise PolicyHttpError(413, "POLICY_INVALID", [{"field": "$", "code": "max_bytes"}], request_id)
        try:
            created = service.create_version(policy_id, raw, actor.principal_id)
        except InvalidPolicy as exc:
            raise PolicyHttpError(422, "POLICY_INVALID", _details(exc.errors), request_id) from exc
        except PolicyConflict as exc:
            raise PolicyHttpError(409, exc.code, request_id=request_id) from exc
        except PolicyUnavailable as exc:
            raise PolicyHttpError(503, exc.code, request_id=request_id) from exc
        return _json(_summary(created), request_id, 201)

    @router.post("/policies/{policy_id}/activate")
    async def activate(policy_id: str, request: Request) -> JSONResponse:
        request_id = _request_id()
        actor = _admin(actor_provider(), request_id)
        _policy_id(policy_id, request_id)
        raw = await _body(request, request_id)
        try:
            body = ActivateBody.model_validate(_object(raw, request_id))
        except ValidationError as exc:
            raise PolicyHttpError(422, "VALIDATION_ERROR", _pydantic_details(exc), request_id) from exc
        except PolicyHttpError:
            raise
        try:
            snapshot = service.activate(policy_id, body.version, body.expected_active_version, actor.principal_id)
        except PolicyConflict as exc:
            raise PolicyHttpError(409, exc.code, request_id=request_id) from exc
        except PolicyNotFound as exc:
            raise PolicyHttpError(404, "NOT_FOUND", request_id=request_id) from exc
        except PolicyUnavailable as exc:
            raise PolicyHttpError(503, exc.code, request_id=request_id) from exc
        except InvalidPolicy as exc:
            raise PolicyHttpError(422, "VALIDATION_ERROR", _details(exc.errors), request_id) from exc
        return _json(
            {
                "policy_id": snapshot.document.policy_id,
                "version": snapshot.document.version,
                "checksum": snapshot.checksum,
                "active": True,
            },
            request_id,
        )

    return router


def register_policy_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PolicyHttpError)
    async def _policy_error(_request: Request, exc: PolicyHttpError) -> JSONResponse:
        return _problem(exc.status, exc.code, exc.request_id or _request_id(), exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for item in exc.errors()[:50]:
            loc = item.get("loc", ())
            field = ".".join(str(part) for part in loc if part != "body") or "$"
            details.append({"field": field[:256], "code": "invalid_value"})
        return _problem(422, "VALIDATION_ERROR", _request_id(), details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "VALIDATION_ERROR"
        return _problem(exc.status_code, code, _request_id())


def _viewer(actor: PolicyActor | None, request_id: str) -> PolicyActor:
    if actor is None:
        raise PolicyHttpError(401, "UNAUTHENTICATED", request_id=request_id)
    if actor.kind != "human" or "viewer" not in actor.roles:
        raise PolicyHttpError(403, "FORBIDDEN", request_id=request_id)
    return actor


def _admin(actor: PolicyActor | None, request_id: str) -> PolicyActor:
    if actor is None:
        raise PolicyHttpError(401, "UNAUTHENTICATED", request_id=request_id)
    if actor.kind != "human" or "policy_admin" not in actor.roles or not actor.csrf_valid:
        raise PolicyHttpError(403, "FORBIDDEN", request_id=request_id)
    return actor


def _policy_id(value: str, request_id: str) -> None:
    if _SLUG.fullmatch(value) is None:
        raise PolicyHttpError(
            422,
            "VALIDATION_ERROR",
            [{"field": "policy_id", "code": "invalid_value"}],
            request_id,
        )


def _version(value: str, request_id: str) -> int:
    if not value.isdigit():
        raise PolicyHttpError(422, "VALIDATION_ERROR", [{"field": "version", "code": "type"}], request_id)
    number = int(value)
    if not 1 <= number <= 1_000_000:
        raise PolicyHttpError(422, "VALIDATION_ERROR", [{"field": "version", "code": "out_of_range"}], request_id)
    return number


def _list_query(params: Mapping[str, str], request_id: str) -> tuple[int, str | None]:
    unknown = set(params) - {"cursor", "limit"}
    if unknown:
        raise PolicyHttpError(422, "VALIDATION_ERROR", [{"field": "query", "code": "unknown_field"}], request_id)
    raw_limit = params.get("limit", "50")
    if _LIMIT.fullmatch(raw_limit) is None:
        raise PolicyHttpError(422, "VALIDATION_ERROR", [{"field": "limit", "code": "invalid_value"}], request_id)
    limit = int(raw_limit)
    if limit > 100:
        raise PolicyHttpError(422, "VALIDATION_ERROR", [{"field": "limit", "code": "out_of_range"}], request_id)
    cursor = params.get("cursor")
    if cursor is not None and (not cursor or len(cursor) > 256):
        raise PolicyHttpError(422, "VALIDATION_ERROR", [{"field": "cursor", "code": "invalid_value"}], request_id)
    return limit, cursor


async def _body(request: Request, request_id: str) -> bytes:
    raw = await request.body()
    if len(raw) > MAX_HTTP_BODY:
        raise PolicyHttpError(413, "POLICY_INVALID", [{"field": "$", "code": "max_bytes"}], request_id)
    return raw


def _object(raw: bytes, request_id: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyHttpError(
            422,
            "VALIDATION_ERROR",
            [{"field": "$", "code": "unsupported_type"}],
            request_id,
        ) from exc

    def pairs(items: list[tuple[Any, Any]]) -> dict[str, Any]:
        mapping: dict[str, Any] = {}
        for key, value in items:
            if not isinstance(key, str) or key in mapping:
                raise PolicyHttpError(422, "VALIDATION_ERROR", [{"field": "$", "code": "duplicate_key"}], request_id)
            mapping[key] = value
        return mapping

    try:
        data = json.loads(text, object_pairs_hook=pairs)
    except PolicyHttpError:
        raise
    except json.JSONDecodeError as exc:
        raise PolicyHttpError(422, "VALIDATION_ERROR", [{"field": "$", "code": "invalid_syntax"}], request_id) from exc
    if not isinstance(data, dict):
        raise PolicyHttpError(422, "VALIDATION_ERROR", [{"field": "$", "code": "type"}], request_id)
    return data


def _json(body: dict[str, object], request_id: str, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers={"X-Request-Id": request_id})


def _summary(item: Any) -> dict[str, object]:
    return {
        "policy_id": item.policy_id,
        "version": item.version,
        "checksum": item.checksum,
        "active": item.active,
        "created_at": item.created_at,
        "created_by": item.created_by,
    }


def _details(errors: tuple[Any, ...] | list[Any]) -> list[dict[str, str]]:
    return [{"field": item.field, "code": item.code} for item in list(errors)[:50]]


def _pydantic_details(exc: ValidationError) -> list[dict[str, str]]:
    details = []
    for item in exc.errors()[:50]:
        loc = item.get("loc", ())
        field = ".".join(str(part) for part in loc) or "$"
        details.append({"field": field[:256], "code": "invalid_value"})
    return details or [{"field": "$", "code": "invalid_value"}]


def _problem(status: int, code: str, request_id: str, details: list[dict[str, str]] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": _MESSAGES.get(code, "La operación no se completó."),
                "request_id": request_id,
                "details": details or [],
            }
        },
        headers={"X-Request-Id": request_id},
    )


def _request_id() -> str:
    return str(uuid.uuid4())
