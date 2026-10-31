"""Engine SQLite, transacciones explícitas, migraciones y copias de seguridad."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, event

BUSY_TIMEOUT_MS = 5000
ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"


def create_sqlite_engine(path: Path) -> Engine:
    """Crea un engine sin abrir conexiones; cada conexión aplica los pragmas."""
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _configure(dbapi_connection: Any, _record: Any) -> None:
        # Autocommit del driver: las transacciones las abre _begin de forma explícita.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin(connection: Connection) -> None:
        mode = connection.get_execution_options().get("wallba_begin", "DEFERRED")
        connection.exec_driver_sql(f"BEGIN {mode}")

    return engine


@contextmanager
def write_transaction(engine: Engine) -> Iterator[Connection]:
    """Transacción con BEGIN IMMEDIATE: serializa a los escritores."""
    with engine.connect().execution_options(wallba_begin="IMMEDIATE") as connection:
        with connection.begin():
            yield connection


def alembic_config(db_path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", ALEMBIC_DIR.as_posix())
    config.attributes["database_url"] = f"sqlite:///{db_path.as_posix()}"
    return config


def run_migrations(db_path: Path, revision: str = "head") -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(db_path), revision)


def backup_database(source: Path, destination: Path) -> Path:
    """Copia consistente con la API de backup de SQLite; nunca sobrescribe."""
    if destination.exists():
        raise FileExistsError(f"el destino de backup ya existe: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return destination


def restore_to_copy(backup: Path, destination: Path) -> Path:
    """Restaura un backup en un archivo nuevo; jamás sobre una base existente."""
    return backup_database(backup, destination)
