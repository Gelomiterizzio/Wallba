"""Puerto de persistencia de identidad.

Solo declara firmas. No hay SQLite ni SQLAlchemy en este módulo. El servicio
abre las sesiones; este puerto no genera tokens ni verifica contraseñas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from wallba.auth.models import AgentCredentialRecord, HumanRecord, SessionRecord


class AuthStateConflict(RuntimeError):
    """A principal was disabled or removed before the session was committed."""


class AuthRepository(Protocol):
    """Almacenamiento de humanos, credenciales de agente y sesiones."""

    def get_human_by_username(self, username: str) -> HumanRecord | None:
        """Busca un humano por nombre de usuario exacto."""
        ...

    def get_human_by_principal_id(self, principal_id: str) -> HumanRecord | None:
        """Busca un humano por su identificador. La sesión no guarda el username."""
        ...

    def get_agent_by_token_hash(self, token_hash: str) -> AgentCredentialRecord | None:
        """Busca una credencial de agente por el hash del bearer."""
        ...

    def insert_session(self, session: SessionRecord) -> None:
        """Inserta una sesión ya construida. No genera tokens."""
        ...

    def get_session(self, token_hash: str) -> SessionRecord | None:
        """Recupera una sesión por el hash de su token opaco."""
        ...

    def revoke_session(self, token_hash: str, revoked_at: datetime) -> None:
        """Marca una sesión como revocada en un instante UTC."""
        ...

    def revoke_sessions_for_principal(
        self, principal_id: str, revoked_at: datetime
    ) -> None:
        """Revoca las sesiones vigentes de un principal."""
        ...

    def update_session(self, session: SessionRecord) -> bool | None:
        """Sustituye el registro de una sesión existente."""
        ...
