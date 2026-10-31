"""Refresh server-side authority in the SAME transaction as the effect claim."""

from sqlalchemy import select

from wallba.auth.schema import credentials, principals
from wallba.contracts.ports import Principal
from wallba.foundation.http import ApiError
from wallba.foundation.models import AgentRow


def refresh_identity(connection, principal, call, credential_hash=None):
    human_or_agent = (
        connection.execute(
            select(principals).where(
                principals.c.id == principal.principal_id,
                principals.c.disabled.is_(False),
                principals.c.kind == principal.kind,
            )
        )
        .mappings()
        .first()
    )
    if human_or_agent is None:
        raise ApiError(403, "SCOPE_DENIED", "Identidad revocada o no autorizada")
    roles = human_or_agent["roles_json"] if principal.kind == "human" else []
    if principal.kind == "human" and "operator" not in roles:
        raise ApiError(403, "ROLE_DENIED", "Se requiere rol operator")
    agent = (
        connection.execute(
            select(AgentRow.__table__).where(
                AgentRow.id == call.agent_id,
                AgentRow.status == "ACTIVE",
            )
        )
        .mappings()
        .first()
    )
    if (
        agent is None
        or call.tool not in agent["tools_json"]
        or call.resource_id not in agent["resource_scopes_json"]
    ):
        raise ApiError(403, "SCOPE_DENIED", "Herramienta o recurso fuera del alcance")
    if principal.kind == "agent":
        if credential_hash is None:
            raise ApiError(
                403, "SCOPE_DENIED", "Se requiere credencial de agente vinculada"
            )
        records = (
            connection.execute(
                select(credentials).where(
                    credentials.c.principal_id == principal.principal_id,
                    credentials.c.agent_id == call.agent_id,
                    credentials.c.revoked_at.is_(None),
                    credentials.c.token_hash == credential_hash,
                )
            )
            .mappings()
            .all()
        )
        pair = {"tool": call.tool, "resource_id": call.resource_id}
        if not any(pair in record["scopes_json"] for record in records):
            raise ApiError(403, "SCOPE_DENIED", "Credencial fuera del alcance")
    return Principal(
        principal_id=principal.principal_id, kind=principal.kind, roles=roles
    )
