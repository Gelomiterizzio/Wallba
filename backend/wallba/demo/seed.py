"""Prepara una instalación de demo: usuarios, agentes y política activa.

Las contraseñas son aleatorias y se muestran una sola vez. Es idempotente: lo que
ya existe no se toca, y una contraseña ya creada no se puede volver a consultar.

Uso: python -m wallba.demo.seed [--agent-bearer-file RUTA]
"""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from wallba.agent.service import seed_agents
from wallba.auth.clock import SystemClock
from wallba.auth.models import AgentCredentialRecord, HumanRecord, Role, Scope
from wallba.auth.passwords import Argon2PasswordHasher
from wallba.auth.persistence import SqlAlchemyAuthRepository
from wallba.auth.tokens import hash_opaque_token
from wallba.foundation.config import load_settings
from wallba.foundation.database import create_sqlite_engine, run_migrations
from wallba.gateway.audit import TransactionalOutbox
from wallba.observability.adapters import AuditFanout, PolicyAuditSink
from wallba.observability.writer import AuditWriter
from wallba.policy.loader import load_policy
from wallba.policy.repository import SqlitePolicyRepository
from wallba.policy.service import PolicyService

ROOT = Path(__file__).resolve().parents[3]
DEMO_POLICY = ROOT / "policies" / "demo.yaml"
SEED_ACTOR = "wallba-seed"
DEMO_USERS = {
    "demo-operator": {Role.VIEWER, Role.OPERATOR},
    "demo-approver": {Role.VIEWER, Role.APPROVER},
    "demo-policy-admin": {Role.VIEWER, Role.POLICY_ADMIN},
    "demo-viewer": {Role.VIEWER},
}
DEMO_AGENT_SCOPES = {
    Scope("file.read", "file:public-guide"),
    Scope("file.read", "file:restricted-ledger"),
    Scope("email.send", "mailbox:demo-outbox"),
    Scope("record.delete", "table:demo-records"),
    Scope("db.query", "query:demo-records"),
}


def seed_users(repository: SqlAlchemyAuthRepository) -> dict[str, str]:
    """Crea las cuentas que falten y devuelve solo las contraseñas recién generadas."""
    hasher = Argon2PasswordHasher()
    created: dict[str, str] = {}
    for username, roles in DEMO_USERS.items():
        if repository.get_human_by_username(username) is not None:
            continue
        password = secrets.token_urlsafe(18)
        repository.add_human(HumanRecord(username, username, hasher.hash_password(password), frozenset(roles), False))
        created[username] = password
    return created


def seed_agent_credential(repository: SqlAlchemyAuthRepository, bearer: str) -> bool:
    token_hash = hash_opaque_token(bearer)
    if repository.get_agent_by_token_hash(token_hash) is not None:
        return False
    repository.add_agent_credential(
        AgentCredentialRecord(token_hash, "demo-agent", "demo-agent", frozenset(DEMO_AGENT_SCOPES), None)
    )
    return True


def seed_policy(db_path: Path) -> str | None:
    """Publica y activa la política de demo si aún no hay ninguna activa."""
    repository = SqlitePolicyRepository(db_path)
    service = PolicyService(repository, SystemClock(), PolicyAuditSink(AuditFanout(TransactionalOutbox(), AuditWriter())))
    if service.get_active_snapshot() is not None:
        return None
    report = load_policy(DEMO_POLICY.read_bytes(), "yaml")
    document = report.document
    if document is None:
        raise ValueError("policies/demo.yaml no es válida")
    if repository.get_version(document.policy_id, document.version) is None:
        service.create_version(document.policy_id, json.dumps(report.normalized_policy()).encode("utf-8"), SEED_ACTOR)
    return service.activate(document.policy_id, document.version, None, SEED_ACTOR).checksum


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-bearer-file", type=Path, default=None)
    args = parser.parse_args(argv)

    settings = load_settings()
    db_path = settings.control_db_path
    run_migrations(db_path)
    engine = create_sqlite_engine(db_path)
    try:
        seed_agents(engine)
        repository = SqlAlchemyAuthRepository(engine)
        passwords = seed_users(repository)
        if args.agent_bearer_file is not None:
            seed_agent_credential(repository, args.agent_bearer_file.read_text(encoding="ascii").strip())
    finally:
        engine.dispose()
    checksum = seed_policy(db_path)

    print(f"Política activa: {'sin cambios' if checksum is None else checksum}")
    if not passwords:
        print("Usuarios: ya existían; sus contraseñas no se pueden volver a mostrar.")
    for username, password in passwords.items():
        print(f"{username}\t{password}")
    if passwords:
        print("Guarda estas contraseñas: no se volverán a mostrar.")


if __name__ == "__main__":
    main()
