"""Handlers de autenticación sin framework y sin socket.

No importan FastAPI al cargar el módulo. El CSRF de logout llega solo en la
cabecera X-CSRF-Token; el adaptador entrega ese valor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from wallba.auth.models import (
    PAYLOAD_TOO_LARGE,
    VALIDATION_ERROR,
    AuthError,
)
from wallba.auth.passwords import AuthDependencyError
from wallba.auth.service import (
    COOKIE_MAX_AGE,
    AuthService,
    log_auth_event,
)

# Códigos y límites documentados en API_CONTRACTS y AUTH_IMPLEMENTATION.
_MAX_BODY_BYTES: int = 65536
_USERNAME_MIN: int = 1
_USERNAME_MAX: int = 128
_PASSWORD_MIN: int = 1
_PASSWORD_MAX: int = 1024
_LOGIN_FIELDS: frozenset[str] = frozenset({"username", "password"})
_VALIDATION_MESSAGE: str = "La solicitud no es válida."
_PAYLOAD_MESSAGE: str = "Carga demasiado grande."


@dataclass(frozen=True, slots=True)
class SessionCookie:
    """Cookie de sesión. El valor no se repite en el cuerpo JSON."""

    name: str
    value: str
    http_only: bool
    secure: bool
    same_site: Literal["strict"]
    path: str
    max_age: int

    def __repr__(self) -> str:
        return (
            "SessionCookie("
            f"name={self.name!r}, value='[redacted]', http_only={self.http_only!r}, "
            f"secure={self.secure!r}, same_site={self.same_site!r}, "
            f"path={self.path!r}, max_age={self.max_age!r})"
        )


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Respuesta ya decidida, lista para un adaptador que este bloque no arranca."""

    status_code: int
    body: dict[str, Any] | None = field(repr=False)
    set_cookie: SessionCookie | None = None
    clear_cookie: bool = False


class _DuplicateKeyError(Exception):
    """Clave JSON repetida. El mensaje es el nombre del campo, no su valor."""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field: str = field


def handle_login(
    service: AuthService,
    raw_body: bytes,
    origin: str | None,
    rate_subject: str,
    request_id: str,
) -> HttpResponse:
    """Valida el cuerpo y, solo si es válido, llama al login.

    No exige cabecera CSRF. El éxito es 200 con exactamente csrf_token y
    roles. La cookie va aparte y no entra en el JSON.
    """
    if not isinstance(raw_body, (bytes, bytearray)):
        raise TypeError("El cuerpo de login debe ser bytes.")
    payload = bytes(raw_body)
    if len(payload) > _MAX_BODY_BYTES:
        log_auth_event("login_rejected", request_id, PAYLOAD_TOO_LARGE)
        return _error_response(
            AuthError(
                status_code=413,
                code=PAYLOAD_TOO_LARGE,
                message=_PAYLOAD_MESSAGE,
                request_id=request_id,
            )
        )
    parsed = _parse_login_body(payload, request_id)
    if isinstance(parsed, AuthError):
        log_auth_event("login_rejected", request_id, VALIDATION_ERROR)
        return _error_response(parsed)
    result = service.login(
        parsed["username"],
        parsed["password"],
        origin,
        rate_subject,
        request_id,
    )
    if isinstance(result, AuthError):
        return _error_response(result)
    return HttpResponse(
        status_code=200,
        body={
            "csrf_token": result.csrf_token,
            "roles": [role.value for role in result.roles],
        },
        set_cookie=_session_cookie(service, result.session_token),
    )


def handle_logout(
    service: AuthService,
    cookie_header: str | None,
    csrf_header: str | None,
    origin: str | None,
    request_id: str,
) -> HttpResponse:
    """Cierra sesión. El CSRF sale de la cabecera y la sesión, de la cookie.

    Un cuerpo JSON, aunque trajera el token, no participa: este handler no
    lo recibe. El éxito es 204 sin cuerpo y con clear_cookie.
    """
    raw_session = _read_cookie(cookie_header, service.settings.cookie_name)
    result = service.logout(raw_session, csrf_header, origin, request_id)
    if isinstance(result, AuthError):
        return _error_response(result)
    return HttpResponse(status_code=204, body=None, clear_cookie=True)


def handle_me(
    service: AuthService,
    cookie_header: str | None,
    request_id: str,
) -> HttpResponse:
    """Devuelve la identidad y el CSRF estable de la sesión.

    La cookie de sesión no se rota aquí. El cuerpo trae el csrf_token derivado
    y no incluye el valor de la cookie.
    """
    raw_session = _read_cookie(cookie_header, service.settings.cookie_name)
    result = service.me(raw_session, request_id)
    if isinstance(result, AuthError):
        return _error_response(result)
    return HttpResponse(
        status_code=200,
        body={
            "principal_id": result.principal_id,
            "username": result.username,
            "kind": result.kind,
            "roles": [role.value for role in result.roles],
            "csrf_token": result.csrf_token,
        },
    )


def build_fastapi_router(service: AuthService) -> Any:
    """Construye un router real sin abrir sockets ni crear otra aplicación."""
    try:
        from wallba.auth.routes import build_router
    except ImportError as exc:
        raise AuthDependencyError(
            "Falta fastapi y no está fijado en el lock. "
            "Este adaptador no abre un socket ni está verificado."
        ) from exc
    return build_router(service)


def _parse_login_body(raw_body: bytes, request_id: str) -> dict[str, str] | AuthError:
    try:
        parsed = json.loads(raw_body, object_pairs_hook=_reject_duplicate_keys)
    except _DuplicateKeyError as exc:
        field_name = exc.field if exc.field in _LOGIN_FIELDS else "body"
        return _validation_error(request_id, ((field_name, "duplicate_key"),))
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        return _validation_error(request_id, (("body", "invalid_type"),))
    if not isinstance(parsed, dict):
        return _validation_error(request_id, (("body", "invalid_type"),))
    details = _login_field_details(parsed)
    if details:
        return _validation_error(request_id, details)
    username = parsed["username"]
    password = parsed["password"]
    if not isinstance(username, str) or not isinstance(password, str):
        return _validation_error(request_id, (("body", "invalid_type"),))
    return {"username": username, "password": password}


def _login_field_details(parsed: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    details: list[tuple[str, str]] = []
    if "username" not in parsed:
        details.append(("username", "required"))
    else:
        details.extend(
            _text_details(parsed["username"], "username", _USERNAME_MIN, _USERNAME_MAX)
        )
    if "password" not in parsed:
        details.append(("password", "required"))
    else:
        details.extend(
            _text_details(parsed["password"], "password", _PASSWORD_MIN, _PASSWORD_MAX)
        )
    for field_name in parsed:
        if field_name not in _LOGIN_FIELDS:
            details.append(("body", "unknown_field"))
    return tuple(details)


def _text_details(
    value: Any, field: str, minimum: int, maximum: int
) -> tuple[tuple[str, str], ...]:
    if isinstance(value, bool) or not isinstance(value, str):
        return ((field, "invalid_type"),)
    if len(value) < minimum or len(value) > maximum:
        return ((field, "invalid_length"),)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return ((field, "invalid_text"),)
    return ()


def _reject_duplicate_keys(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise json.JSONDecodeError("La clave JSON no es texto.", "", 0)
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _validation_error(
    request_id: str, details: tuple[tuple[str, str], ...]
) -> AuthError:
    return AuthError(
        status_code=422,
        code=VALIDATION_ERROR,
        message=_VALIDATION_MESSAGE,
        request_id=request_id,
        details=details,
    )


def _error_response(error: AuthError) -> HttpResponse:
    return HttpResponse(
        status_code=error.status_code,
        body={
            "error": {
                "code": error.code,
                "message": error.message,
                "request_id": error.request_id,
                "details": [
                    {"field": field, "code": code} for field, code in error.details
                ],
            }
        },
    )


def _session_cookie(service: AuthService, session_token: str) -> SessionCookie:
    settings = service.settings
    return SessionCookie(
        name=settings.cookie_name,
        value=session_token,
        http_only=True,
        secure=settings.cookie_secure,
        same_site="strict",
        path=settings.cookie_path,
        max_age=COOKIE_MAX_AGE,
    )


def _read_cookie(cookie_header: str | None, cookie_name: str) -> str | None:
    """Lee la cookie configurada separando por ';' y el primer '='."""
    if cookie_header is None or cookie_header == "":
        return None
    found = []
    for part in cookie_header.split(";"):
        segment = part.strip()
        if segment == "":
            continue
        name, separator, value = segment.partition("=")
        if separator == "=" and name == cookie_name:
            found.append(value)
    return found[0] if len(found) == 1 else None
