"""Formato común de errores, paginación y dependencias HTTP."""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from wallba.contracts.api import ErrorBody, ErrorDetail, ErrorResponse
from wallba.contracts.ports import AuditSink, HumanAuthorizer, Principal, Role, ScenarioHarness, ToolGateway

T = TypeVar("T")
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_PAGE = 100
DEFAULT_PAGE = 50


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass
class Integrations:
    """Puertos de otros dueños. Si falta uno, sus rutas fallan cerrado con 503."""

    authorizer: HumanAuthorizer | None = None
    gateway: ToolGateway | None = None
    audit: AuditSink | None = None
    harness: ScenarioHarness | None = None
    policy_ready: Callable[[], bool] | None = None
    extra_routers: list[Any] = field(default_factory=list)


def _error_response(
    status_code: int, code: str, message: str, details: Sequence[ErrorDetail] = ()
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, request_id=str(uuid.uuid4()), details=list(details))
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            ErrorDetail(field=".".join(str(p) for p in item["loc"]), code=item["type"])
            for item in exc.errors()
        ]
        return _error_response(422, "VALIDATION_ERROR", "La solicitud no cumple el contrato", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(exc.status_code, "HTTP_ERROR", "Solicitud no atendida")

    @app.exception_handler(Exception)
    async def _unexpected(_request: Request, _exc: Exception) -> JSONResponse:
        # Sin stacktrace ni detalle interno en la respuesta.
        return _error_response(500, "INTERNAL_ERROR", "Error interno")


def install_payload_limit(app: FastAPI) -> None:
    @app.middleware("http")
    async def _limit(request: Request, call_next):
        declared = request.headers.get("content-length")
        too_large = declared is not None and declared.isdigit() and int(declared) > MAX_PAYLOAD_BYTES
        if not too_large and declared is None and request.method in {"POST", "PUT", "PATCH"}:
            too_large = len(await request.body()) > MAX_PAYLOAD_BYTES
        if too_large:
            return _error_response(413, "PAYLOAD_TOO_LARGE", "La solicitud supera el límite")
        return await call_next(request)


def integrations_of(request: Request) -> Integrations:
    return request.app.state.integrations


def require_role(role: Role, *, mutation: bool = False) -> Callable[[Request], Principal]:
    """RBAC y CSRF los implementa P3; sin autorizador, falla cerrado."""

    def dependency(request: Request) -> Principal:
        authorizer = integrations_of(request).authorizer
        if authorizer is None:
            raise ApiError(503, "AUTHORIZATION_UNAVAILABLE", "Autorización no disponible")
        return authorizer.require(request, role, mutation=mutation)

    return dependency


def encode_cursor(key: str) -> str:
    return base64.urlsafe_b64encode(key.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> str:
    try:
        return base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True).decode("utf-8")
    except (binascii.Error, UnicodeError, ValueError) as exc:
        raise ApiError(422, "VALIDATION_ERROR", "Cursor inválido") from exc


def paginate(
    items: Sequence[T], key: Callable[[T], str], cursor: str | None, limit: int
) -> tuple[list[T], str | None]:
    """Pagina una secuencia ya ordenada por `key` descendente."""
    start = 0
    if cursor is not None:
        after = decode_cursor(cursor)
        start = next((index for index, item in enumerate(items) if key(item) < after), len(items))
    page = list(items[start : start + limit])
    has_more = start + limit < len(items)
    return page, encode_cursor(key(page[-1])) if has_more and page else None
