"""Persona 3 local identity provisioning. Never creates known-password defaults."""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
from pathlib import Path

from wallba.auth.models import HumanRecord, Role, ensure_identifier
from wallba.auth.passwords import Argon2PasswordHasher
from wallba.auth.persistence import SqlAlchemyAuthRepository
from wallba.foundation.database import create_sqlite_engine, run_migrations


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Persona 3 — administrar identidades locales"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.getenv("WALLBA_DATA_DIR", ".local/person3")) / "control.sqlite",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user")
    create.add_argument("--principal-id", required=True)
    create.add_argument("--username", required=True)
    create.add_argument(
        "--roles", nargs="+", choices=[item.value for item in Role], required=True
    )
    args = parser.parse_args()
    try:
        ensure_identifier(args.principal_id)
    except ValueError as exc:
        parser.error(str(exc))
    if not 1 <= len(args.username) <= 128 or args.username.strip() != args.username:
        parser.error("Username inválido (1..128 caracteres, sin espacios exteriores).")
    password = getpass.getpass("Contraseña nueva (mínimo 12 caracteres): ")
    confirmation = getpass.getpass("Repite la contraseña: ")
    if not 12 <= len(password) <= 1024 or not secrets.compare_digest(
        password.encode(), confirmation.encode()
    ):
        parser.error("La contraseña o su confirmación no son válidas.")
    path = args.db.resolve()
    run_migrations(path)
    engine = create_sqlite_engine(path)
    try:
        SqlAlchemyAuthRepository(engine).add_human(
            HumanRecord(
                args.principal_id,
                args.username,
                Argon2PasswordHasher().hash_password(password),
                frozenset(Role(role) for role in args.roles),
                False,
            )
        )
    finally:
        engine.dispose()
    print("Persona 3: usuario creado sin registrar contraseña ni tokens.")


if __name__ == "__main__":
    main()
