"""Persona 3 implementation of P1's HumanAuthorizer integration port."""

from __future__ import annotations

from uuid import uuid4

from wallba.auth.authorization import authenticate_agent, require_scope
from wallba.auth.clock import SystemClock
from wallba.auth.http_handlers import _read_cookie
from wallba.auth.models import AgentPrincipal, AuthError
from wallba.auth.passwords import Argon2PasswordHasher
from wallba.auth.persistence import SqlAlchemyAuthRepository, SqliteLoginRateLimiter
from wallba.auth.service import IDLE, AuthService, AuthSettings
from wallba.auth.tokens import hash_opaque_token, token_matches
from wallba.contracts.ports import Principal
from wallba.foundation.http import ApiError


def _raise(error: AuthError) -> None:
    raise ApiError(error.status_code, error.code, error.message)


def create_auth(
    engine,
    settings: AuthSettings,
    *,
    clock=None,
    hasher=None,
    login_attempts=10,
    login_window_seconds=300,
) -> AuthService:
    return AuthService(
        SqlAlchemyAuthRepository(engine),
        clock or SystemClock(),
        hasher or Argon2PasswordHasher(),
        SqliteLoginRateLimiter(engine, login_attempts, login_window_seconds),
        settings,
    )


class HumanAuthorizer:
    """Identity is resolved on every call; no test headers or body roles are trusted."""

    def __init__(self, service: AuthService):
        self.service = service

    def require(self, request, role: str, *, mutation: bool) -> Principal:
        principal = self.authenticate(request)
        if role not in principal.roles:
            raise ApiError(
                403, "ROLE_DENIED", "Permiso insuficiente para esta operación."
            )
        if mutation:
            self.require_csrf(request)
        return principal

    def authenticate(self, request) -> Principal:
        """Authenticated live human, without asserting a particular role."""
        request_id = str(uuid4())
        authorization = request.headers.get("authorization")
        if authorization is not None:
            # An agent bearer must never gain authority through a cookie on the same request.
            raise ApiError(
                403, "ROLE_DENIED", "Se requiere una sesión humana autorizada."
            )
        raw_session = _read_cookie(
            request.headers.get("cookie"), self.service.settings.cookie_name
        )
        human = self.service.authenticate_human(raw_session, request_id)
        if isinstance(human, AuthError):
            _raise(human)
        return Principal(
            principal_id=human.principal_id,
            kind="human",
            roles=sorted(item.value for item in human.roles),
        )

    def require_csrf(self, request, raw_session: str | None = None) -> None:
        if raw_session is None:
            raw_session = _read_cookie(
                request.headers.get("cookie"), self.service.settings.cookie_name
            )
        if request.headers.get("origin") not in self.service.settings.allowed_origins:
            raise ApiError(403, "ORIGIN_REJECTED", "Origen rechazado.")
        if raw_session is None:
            raise ApiError(401, "AUTHENTICATION_REQUIRED", "Autenticación requerida.")
        record = self.service.repository.get_session(hash_opaque_token(raw_session))
        now = self.service._now()
        if (
            record is None
            or record.revoked_at is not None
            or now >= record.expires_at
            or now >= record.last_seen_at + IDLE
        ):
            raise ApiError(401, "AUTHENTICATION_REQUIRED", "Autenticación requerida.")
        if not token_matches(record.csrf_hash, request.headers.get("x-csrf-token")):
            raise ApiError(403, "CSRF_REJECTED", "CSRF rechazado.")

    def require_agent(self, request) -> AgentPrincipal:
        if len(request.headers.getlist("authorization")) != 1:
            raise ApiError(
                401, "AUTHENTICATION_REQUIRED", "Credencial de agente requerida."
            )
        header = request.headers.get("authorization", "")
        scheme, separator, raw = header.partition(" ")
        if not separator or scheme.lower() != "bearer" or not raw or " " in raw:
            raise ApiError(
                401, "AUTHENTICATION_REQUIRED", "Credencial de agente requerida."
            )
        principal = authenticate_agent(self.service.repository, raw, str(uuid4()))
        if isinstance(principal, AuthError):
            _raise(principal)
        return principal

    def require_agent_scope(
        self, request, tool: str, resource_id: str
    ) -> AgentPrincipal:
        principal = self.require_agent(request)
        allowed = require_scope(principal, tool, resource_id, str(uuid4()))
        if isinstance(allowed, AuthError):
            _raise(allowed)
        return allowed
