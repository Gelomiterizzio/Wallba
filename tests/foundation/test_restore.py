"""Backup y restore siempre sobre copia (WAL-P1-010)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from wallba.foundation.database import (
    backup_database,
    create_sqlite_engine,
    restore_to_copy,
    run_migrations,
    write_transaction,
)


def _count_agents(path: Path) -> int:
    engine = create_sqlite_engine(path)
    with engine.connect() as connection:
        count = connection.execute(text("SELECT COUNT(*) FROM agents")).scalar_one()
    engine.dispose()
    return count


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "control.sqlite"
    run_migrations(path)
    engine = create_sqlite_engine(path)
    with write_transaction(engine) as connection:
        connection.execute(
            text(
                "INSERT INTO agents (id, name, tools_json, resource_scopes_json, status) "
                "VALUES ('demo-agent', 'Demo', '[]', '[]', 'ACTIVE')"
            )
        )
    engine.dispose()
    return path


def test_backup_and_restore_recover_data_on_a_copy(tmp_path: Path, database: Path) -> None:
    backup = backup_database(database, tmp_path / "backups" / "control.bak")
    engine = create_sqlite_engine(database)
    with write_transaction(engine) as connection:
        connection.execute(text("DELETE FROM agents"))
    engine.dispose()
    assert _count_agents(database) == 0

    restored = restore_to_copy(backup, tmp_path / "restored.sqlite")

    assert _count_agents(restored) == 1
    assert _count_agents(database) == 0


def test_restore_never_overwrites_an_existing_database(tmp_path: Path, database: Path) -> None:
    backup = backup_database(database, tmp_path / "control.bak")
    with pytest.raises(FileExistsError):
        restore_to_copy(backup, database)
    assert _count_agents(database) == 1


def test_backup_never_overwrites(tmp_path: Path, database: Path) -> None:
    backup_database(database, tmp_path / "control.bak")
    with pytest.raises(FileExistsError):
        backup_database(database, tmp_path / "control.bak")
