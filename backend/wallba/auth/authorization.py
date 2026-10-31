"""Autenticación de agentes y autorización humana de aprobación.

No llama ejecutores, aprobaciones ni herramientas. No abre sesiones.
Códigos de rechazo definidos en API_CONTRACTS. Esta compuerta no sustituye
la comprobación de no autoaprobación ni el consumo CAS del futuro módulo approvals.
"""

from __future__ import annotations

from wallba.auth.models import (
    AUTHENTICATION_REQUIRED,
    CSRF_REJECTED,
    ORIGIN_REJECTED,
    ROLE_DENIED,
    SCOPE_DENIED,
    AgentPrincipal,
    AuthError,
    HumanPrincipal,
    Principal,
    Role,
    Scope,
)
from wallba.auth.repository import AuthRepository
from wallba.auth.tokens import hash_opaque_token, token_matches

_INVALID_CREDENTIALS: str = "Credenciales no válidas."
_SCOPE_DENIED: str = "Alcance denegado."
_ROLE_DENIED: str = "Permiso denegado."
_ORIGIN_REJECTED: str = "Origen rechazado."
_CSRF_REJECTED: str = "CSRF rechazado."


def human_roles(principal: Principal) -> frozenset[Role]:
    """Devuelve los roles del humano. Un agente no tiene roles."""
    if isinstance(principal, HumanPrincipal):
        return principal.roles
    return frozenset()


def authenticate_agent(
    repository: AuthRepository,
    raw_bearer: str | None,
    request_id: str,
) -> AgentPrincipal | AuthError:
    """Resuelve un bearer de agente o un 401 indistinguible.

    Bearer ausente, desconocido o revocado comparten estado, código y mensaje.
    El error no incluye el bearer. El principal resultante no copia roles.
    """
    if raw_bearer is None or raw_bearer == "":
        return _authentication_required(request_id)
    record = repository.get_agent_by_token_hash(hash_opaque_token(raw_bearer))
    if record is None or record.revoked_at is not None:
        return _authentication_required(request_id)
    return AgentPrincipal(
        principal_id=record.principal_id,
        agent_id=record.agent_id,
        scopes=record.scopes,
    )


def require_scope(
    principal: Principal,
    tool: str,
    resource_id: str,
    request_id: str,
) -> AgentPrincipal | AuthError:
    """Exige el par exacto herramienta/recurso sobre un agente.

    Un humano, u otro par distinto, recibe 403 SCOPE_DENIED. No hay comodines.
    """
    if (
        isinstance(principal, AgentPrincipal)
        and Scope(tool, resource_id) in principal.scopes
    ):
        return principal
    return AuthError(
        status_code=403,
        code=SCOPE_DENIED,
        message=_SCOPE_DENIED,
        request_id=request_id,
    )


def authorize_human_approval(
    principal: Principal,
    *,
    csrf_token: str | None,
    csrf_hash: str,
    origin: str | None,
    allowed_origins: frozenset[str],
    request_id: str,
) -> HumanPrincipal | AuthError:
    """Autoriza una aprobación humana o devuelve el primer rechazo aplicable.

    El orden es rol, origen y CSRF. Una lista de orígenes vacía deniega
    siempre. Esta función no recibe ni ejecuta un efecto.
    """
    if (
        not isinstance(principal, HumanPrincipal)
        or Role.APPROVER not in principal.roles
    ):
        return AuthError(
            status_code=403,
            code=ROLE_DENIED,
            message=_ROLE_DENIED,
            request_id=request_id,
        )
    if origin is None or origin not in allowed_origins:
        return AuthError(
            status_code=403,
            code=ORIGIN_REJECTED,
            message=_ORIGIN_REJECTED,
            request_id=request_id,
        )
    if not token_matches(csrf_hash, csrf_token):
        return AuthError(
            status_code=403,
            code=CSRF_REJECTED,
            message=_CSRF_REJECTED,
            request_id=request_id,
        )
    return principal


def _authentication_required(request_id: str) -> AuthError:
    return AuthError(
        status_code=401,
        code=AUTHENTICATION_REQUIRED,
        message=_INVALID_CREDENTIALS,
        request_id=request_id,
    )
