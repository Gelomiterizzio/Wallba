"""API pública de identidad y sesión.

Importar este paquete no abre conexiones, no lee relojes, no registra rutas
y no importa FastAPI, Argon2, HTTPX ni SQLAlchemy.
"""

from wallba.auth.authorization import (
    authenticate_agent,
    authorize_human_approval,
    human_roles,
    require_scope,
)
from wallba.auth.clock import Clock, SystemClock
from wallba.auth.http_handlers import (
    HttpResponse,
    SessionCookie,
    build_fastapi_router,
    handle_login,
    handle_logout,
    handle_me,
)
from wallba.auth.models import (
    AUTHENTICATION_REQUIRED,
    CSRF_REJECTED,
    ORIGIN_REJECTED,
    PAYLOAD_TOO_LARGE,
    RATE_LIMITED,
    ROLE_DENIED,
    SCOPE_DENIED,
    VALIDATION_ERROR,
    AgentCredentialRecord,
    AgentPrincipal,
    AuthError,
    HumanPrincipal,
    HumanRecord,
    Principal,
    Role,
    Scope,
    SessionRecord,
    ensure_utc,
    ensure_uuid,
)
from wallba.auth.passwords import (
    Argon2PasswordHasher,
    AuthDependencyError,
    PasswordHasher,
)
from wallba.auth.repository import AuthRepository
from wallba.auth.service import (
    ABSOLUTE_SESSION,
    COOKIE_MAX_AGE,
    IDLE,
    AuthService,
    AuthSettings,
    IssuedSession,
    MeResult,
)
from wallba.auth.tokens import hash_opaque_token, token_matches

__all__ = [
    "ABSOLUTE_SESSION",
    "AUTHENTICATION_REQUIRED",
    "COOKIE_MAX_AGE",
    "CSRF_REJECTED",
    "IDLE",
    "ORIGIN_REJECTED",
    "PAYLOAD_TOO_LARGE",
    "RATE_LIMITED",
    "ROLE_DENIED",
    "SCOPE_DENIED",
    "VALIDATION_ERROR",
    "AgentCredentialRecord",
    "AgentPrincipal",
    "Argon2PasswordHasher",
    "AuthDependencyError",
    "AuthError",
    "AuthRepository",
    "AuthService",
    "AuthSettings",
    "Clock",
    "HttpResponse",
    "HumanPrincipal",
    "HumanRecord",
    "IssuedSession",
    "MeResult",
    "PasswordHasher",
    "Principal",
    "Role",
    "Scope",
    "SessionCookie",
    "SessionRecord",
    "SystemClock",
    "authenticate_agent",
    "authorize_human_approval",
    "build_fastapi_router",
    "ensure_utc",
    "ensure_uuid",
    "handle_login",
    "handle_logout",
    "handle_me",
    "hash_opaque_token",
    "human_roles",
    "require_scope",
    "token_matches",
]
