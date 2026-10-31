"""Modelos de identidad de WALLBA para el bloque de autorización.

Los principales autenticados no transportan secretos. Los registros de
repositorio sí pueden guardar hashes. Este módulo no abre sesiones ni
consulta almacenamiento.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal


class Role(StrEnum):
    """Rol humano asignado por el servidor."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    APPROVER = "approver"
    POLICY_ADMIN = "policy_admin"


@dataclass(frozen=True, slots=True)
class Scope:
    """Par exacto herramienta/recurso. No admite comodines."""

    tool: str
    resource_id: str


@dataclass(frozen=True, slots=True)
class HumanPrincipal:
    """Humano ya autenticado. No incluye contraseña ni hash."""

    principal_id: str
    username: str
    roles: frozenset[Role]
    kind: Literal["human"] = "human"

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal_id", ensure_identifier(self.principal_id))
        if self.kind != "human":
            raise ValueError("El principal humano debe tener kind 'human'.")


@dataclass(frozen=True, slots=True)
class AgentPrincipal:
    """Agente ya autenticado. No tiene roles humanos."""

    principal_id: str
    agent_id: str
    scopes: frozenset[Scope]
    kind: Literal["agent"] = "agent"

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal_id", ensure_identifier(self.principal_id))
        object.__setattr__(self, "agent_id", ensure_identifier(self.agent_id))
        if self.kind != "agent":
            raise ValueError("El principal de agente debe tener kind 'agent'.")


Principal = HumanPrincipal | AgentPrincipal


@dataclass(frozen=True, slots=True)
class HumanRecord:
    """Registro persistible de un humano. No es un principal autenticado."""

    principal_id: str
    username: str
    password_hash: str = field(repr=False)
    roles: frozenset[Role]
    disabled: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal_id", ensure_identifier(self.principal_id))


@dataclass(frozen=True, slots=True)
class AgentCredentialRecord:
    """Credencial de agente. Solo se conserva el hash del bearer."""

    token_hash: str = field(repr=False)
    agent_id: str
    principal_id: str
    scopes: frozenset[Scope]
    revoked_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", ensure_identifier(self.agent_id))
        object.__setattr__(self, "principal_id", ensure_identifier(self.principal_id))
        if self.revoked_at is not None:
            object.__setattr__(self, "revoked_at", ensure_utc(self.revoked_at))


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """Sesión opaca persistida. Guarda hashes, nunca el token ni el CSRF en claro."""

    token_hash: str = field(repr=False)
    principal_id: str
    csrf_hash: str = field(repr=False)
    expires_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal_id", ensure_identifier(self.principal_id))
        object.__setattr__(self, "expires_at", ensure_utc(self.expires_at))
        object.__setattr__(self, "last_seen_at", ensure_utc(self.last_seen_at))
        if self.revoked_at is not None:
            object.__setattr__(self, "revoked_at", ensure_utc(self.revoked_at))


@dataclass(frozen=True, slots=True)
class AuthError:
    """Rechazo de autenticación o autorización, sin secretos ni trazas."""

    status_code: int
    code: str
    message: str
    request_id: str
    details: tuple[tuple[str, str], ...] = ()


# Códigos del contrato auth, fijados en docs/API_CONTRACTS.md.
SCOPE_DENIED: str = "SCOPE_DENIED"
ROLE_DENIED: str = "ROLE_DENIED"
CSRF_REJECTED: str = "CSRF_REJECTED"
ORIGIN_REJECTED: str = "ORIGIN_REJECTED"
AUTHENTICATION_REQUIRED: str = "AUTHENTICATION_REQUIRED"
RATE_LIMITED: str = "RATE_LIMITED"
PAYLOAD_TOO_LARGE: str = "PAYLOAD_TOO_LARGE"
VALIDATION_ERROR: str = "VALIDATION_ERROR"


def ensure_uuid(value: str) -> str:
    """Devuelve el UUID canónico o lanza ValueError si el texto no es válido."""
    if not isinstance(value, str):
        raise ValueError("El identificador debe ser un UUID en texto.")  # noqa: TRY004 - input validation is a ValueError API
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ValueError("El identificador no es un UUID válido.") from exc
    return str(parsed)


def ensure_identifier(value: str) -> str:
    """Shared P1 Identifier: a slug or UUID, at most 64 lowercase characters."""
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value) is None
    ):
        raise ValueError(
            "El principal debe cumplir Identifier de contratos compartidos."
        )
    return value


def ensure_utc(value: datetime) -> datetime:
    """Normaliza un datetime consciente a UTC. Rechaza valores naive."""
    if not isinstance(value, datetime):
        raise ValueError("Se esperaba un datetime.")  # noqa: TRY004 - input validation is a ValueError API
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Se rechaza un datetime naive; se exige UTC consciente.")
    return value.astimezone(UTC)
