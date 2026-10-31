"""Entorno Alembic. La URL llega por configuración, nunca hardcodeada."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from wallba.foundation.models import Base

target_metadata = Base.metadata


def _database_url() -> str:
    url = context.config.attributes.get("database_url")
    if not url:
        raise RuntimeError("falta database_url: usar wallba.foundation.database.run_migrations")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
