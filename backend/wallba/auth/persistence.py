"""SQLAlchemy repository and durable, atomic login attempt reservation."""

from datetime import datetime, timedelta

from sqlalchemy import case, delete, insert, select, update

from wallba.auth.models import (
    AgentCredentialRecord,
    HumanRecord,
    Role,
    Scope,
    SessionRecord,
)
from wallba.auth.repository import AuthStateConflict
from wallba.auth.schema import credentials, login_limits, principals, sessions
from wallba.auth.tokens import hash_opaque_token
from wallba.foundation.database import write_transaction
from wallba.foundation.models import AgentRow

agents = AgentRow.__table__


def stamp(value):
    return value.isoformat() if value is not None else None


def instant(value):
    return datetime.fromisoformat(value) if value is not None else None


class SqlAlchemyAuthRepository:
    def __init__(self, engine):
        self.engine = engine

    def _human(self, condition):
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(principals).where(condition, principals.c.kind == "human")
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return HumanRecord(
            row["id"],
            row["username"],
            row["password_hash"],
            frozenset(Role(role) for role in row["roles_json"]),
            bool(row["disabled"]),
        )

    def get_human_by_username(self, username):
        return self._human(principals.c.username == username)

    def get_human_by_principal_id(self, principal_id):
        return self._human(principals.c.id == principal_id)

    def add_human(self, record):
        with write_transaction(self.engine) as connection:
            connection.execute(
                insert(principals).values(
                    id=record.principal_id,
                    username=record.username,
                    password_hash=record.password_hash,
                    roles_json=sorted(role.value for role in record.roles),
                    disabled=int(record.disabled),
                    kind="human",
                )
            )

    def get_agent_by_token_hash(self, token_hash):
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        credentials,
                        agents.c.tools_json.label("agent_tools"),
                        agents.c.resource_scopes_json.label("agent_resources"),
                    )
                    .join(principals, credentials.c.principal_id == principals.c.id)
                    .join(agents, credentials.c.agent_id == agents.c.id)
                    .where(
                        credentials.c.token_hash == token_hash,
                        agents.c.status == "ACTIVE",
                        principals.c.kind == "agent",
                        principals.c.disabled == 0,
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return AgentCredentialRecord(
            row["token_hash"],
            row["agent_id"],
            row["principal_id"],
            frozenset(
                Scope(**scope)
                for scope in row["scopes_json"]
                if scope.get("tool") in row["agent_tools"]
                and scope.get("resource_id") in row["agent_resources"]
            ),
            instant(row["revoked_at"]),
        )

    def add_agent_credential(self, record: AgentCredentialRecord) -> None:
        """Local provisioning only; never exposed as a tool or public endpoint."""
        with write_transaction(self.engine) as connection:
            agent = (
                connection.execute(
                    select(agents).where(
                        agents.c.id == record.agent_id, agents.c.status == "ACTIVE"
                    )
                )
                .mappings()
                .first()
            )
            if agent is None or any(
                scope.tool not in agent["tools_json"]
                or scope.resource_id not in agent["resource_scopes_json"]
                for scope in record.scopes
            ):
                raise ValueError("Credencial fuera del catálogo de agente activo.")
            existing = (
                connection.execute(
                    select(principals).where(principals.c.id == record.principal_id)
                )
                .mappings()
                .first()
            )
            if existing is None:
                connection.execute(
                    insert(principals).values(
                        id=record.principal_id,
                        username=record.principal_id,
                        password_hash=None,
                        roles_json=[],
                        disabled=False,
                        kind="agent",
                    )
                )
            elif existing["kind"] != "agent" or existing["disabled"]:
                raise ValueError("El principal no es un agente activo.")
            connection.execute(
                insert(credentials).values(
                    token_hash=record.token_hash,
                    principal_id=record.principal_id,
                    agent_id=record.agent_id,
                    scopes_json=[
                        {"tool": scope.tool, "resource_id": scope.resource_id}
                        for scope in sorted(
                            record.scopes,
                            key=lambda item: (item.tool, item.resource_id),
                        )
                    ],
                    revoked_at=stamp(record.revoked_at),
                )
            )

    def insert_session(self, session):
        with write_transaction(self.engine) as connection:
            connection.execute(insert(sessions).values(**self._values(session)))

    def replace_sessions(self, session, now):
        with write_transaction(self.engine) as connection:
            active = connection.execute(
                select(principals.c.id).where(
                    principals.c.id == session.principal_id,
                    principals.c.disabled == 0,
                    principals.c.kind == "human",
                )
            ).first()
            if active is None:
                raise AuthStateConflict(
                    "El principal dejó de estar activo durante el login."
                )
            connection.execute(
                update(sessions)
                .where(
                    sessions.c.principal_id == session.principal_id,
                    sessions.c.revoked_at.is_(None),
                )
                .values(revoked_at=stamp(now))
            )
            connection.execute(insert(sessions).values(**self._values(session)))

    @staticmethod
    def _values(session):
        return {
            "token_hash": session.token_hash,
            "principal_id": session.principal_id,
            "csrf_hash": session.csrf_hash,
            "expires_at": stamp(session.expires_at),
            "last_seen_at": stamp(session.last_seen_at),
            "revoked_at": stamp(session.revoked_at),
        }

    def get_session(self, token_hash):
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(sessions).where(sessions.c.token_hash == token_hash)
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return SessionRecord(
            row["token_hash"],
            row["principal_id"],
            row["csrf_hash"],
            instant(row["expires_at"]),
            instant(row["last_seen_at"]),
            instant(row["revoked_at"]),
        )

    def revoke_session(self, token_hash, revoked_at):
        with write_transaction(self.engine) as connection:
            connection.execute(
                update(sessions)
                .where(
                    sessions.c.token_hash == token_hash, sessions.c.revoked_at.is_(None)
                )
                .values(revoked_at=stamp(revoked_at))
            )

    def revoke_sessions_for_principal(self, principal_id, revoked_at):
        with write_transaction(self.engine) as connection:
            connection.execute(
                update(sessions)
                .where(
                    sessions.c.principal_id == principal_id,
                    sessions.c.revoked_at.is_(None),
                )
                .values(revoked_at=stamp(revoked_at))
            )

    def update_session(self, record):
        # Touch only: a stale /me must NEVER clear revoked_at or rotate CSRF.
        with write_transaction(self.engine) as connection:
            now = stamp(record.last_seen_at)
            active = select(principals.c.id).where(
                principals.c.disabled == 0, principals.c.kind == "human"
            )
            result = connection.execute(
                update(sessions)
                .where(
                    sessions.c.token_hash == record.token_hash,
                    sessions.c.revoked_at.is_(None),
                    sessions.c.principal_id.in_(active),
                    sessions.c.expires_at > now,
                    sessions.c.last_seen_at
                    > stamp(record.last_seen_at - timedelta(minutes=30)),
                )
                .values(
                    last_seen_at=case(
                        (sessions.c.last_seen_at < now, now),
                        else_=sessions.c.last_seen_at,
                    )
                )
            )
            return result.rowcount == 1


class SqliteLoginRateLimiter:
    """Fixed-window budget per socket peer; survives restart and races.

    Every attempt reserves one slot before password verification, including
    successful logins. No client-supplied subject or forwarded header is trusted.
    """

    def __init__(self, engine, max_attempts=10, window_seconds=300):
        self.engine = engine
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_seconds)

    def acquire(self, subject, now):
        key = hash_opaque_token(subject)
        with write_transaction(self.engine) as connection:
            connection.execute(
                delete(login_limits).where(
                    login_limits.c.window_start <= stamp(now - self.window)
                )
            )
            row = (
                connection.execute(
                    select(login_limits).where(login_limits.c.subject_hash == key)
                )
                .mappings()
                .first()
            )
            if row is None:
                connection.execute(
                    insert(login_limits).values(
                        subject_hash=key,
                        window_start=stamp(now),
                        attempts=1,
                    )
                )
                return True
            if row["attempts"] >= self.max_attempts:
                return False
            connection.execute(
                update(login_limits)
                .where(login_limits.c.subject_hash == key)
                .values(attempts=row["attempts"] + 1)
            )
            return True

    def record_failure(self, subject, now):
        pass  # Already counted atomically by acquire().

    def clear(self, subject):
        pass  # Success must not erase the shared peer budget.
