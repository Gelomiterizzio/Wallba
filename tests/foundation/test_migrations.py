"""Migraciones y restricciones de la base de control (WAL-P1-003)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from wallba.foundation.database import alembic_config, create_sqlite_engine, run_migrations, write_transaction


def _insert_demo_run(connection, run_id: str, status: str = "RUNNING") -> None:
    connection.execute(
        text(
            "INSERT INTO demo_runs (run_id, scenario_id, seed, status, baseline_env, protected_env, "
            "created_by, started_at, state_json) VALUES (:id, 'S04', 1, :status, 'b', 'p', 'op', :at, '{}')"
        ),
        {"id": run_id, "status": status, "at": datetime(2026, 10, 31, tzinfo=timezone.utc).isoformat(" ")},
    )


@pytest.fixture
def engine(tmp_path: Path):
    db_path = tmp_path / "control.sqlite"
    run_migrations(db_path)
    value = create_sqlite_engine(db_path)
    yield value
    value.dispose()


def test_migrations_form_a_single_line(tmp_path: Path) -> None:
    # Dos dominios colgando del mismo padre impiden arrancar la API ("Multiple head revisions").
    script = ScriptDirectory.from_config(alembic_config(tmp_path / "control.sqlite"))
    assert len(script.get_heads()) == 1


def test_empty_database_gets_all_tables(engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert {"agents", "agent_runs", "demo_runs", "evidence", "alembic_version"} <= tables


def test_pragmas_are_applied_per_connection(engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000


def test_single_active_run_is_enforced_by_database(engine) -> None:
    with write_transaction(engine) as connection:
        _insert_demo_run(connection, "a")
    with pytest.raises(IntegrityError), write_transaction(engine) as connection:
        _insert_demo_run(connection, "b", "WAITING_APPROVAL")
    with write_transaction(engine) as connection:
        connection.execute(text("UPDATE demo_runs SET status = 'COMPLETED' WHERE run_id = 'a'"))
        _insert_demo_run(connection, "c")


def test_invalid_status_is_rejected(engine) -> None:
    with pytest.raises(IntegrityError), write_transaction(engine) as connection:
        _insert_demo_run(connection, "a", "PASS")


def test_evidence_foreign_key_is_enforced(engine) -> None:
    with pytest.raises(IntegrityError), write_transaction(engine) as connection:
        connection.execute(
            text(
                "INSERT INTO evidence (evidence_id, run_id, manifest_json, manifest_digest, schema_version) "
                "VALUES ('e', 'no-existe', '{}', 'd', '1')"
            )
        )


def test_failed_transaction_rolls_back(engine) -> None:
    with pytest.raises(RuntimeError), write_transaction(engine) as connection:
        _insert_demo_run(connection, "a")
        raise RuntimeError("fallo")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM demo_runs")).scalar_one() == 0


def test_upgrade_keeps_existing_data(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite"
    run_migrations(db_path)
    engine = create_sqlite_engine(db_path)
    with write_transaction(engine) as connection:
        _insert_demo_run(connection, "previo", "COMPLETED")
    engine.dispose()

    run_migrations(db_path)

    engine = create_sqlite_engine(db_path)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT run_id FROM demo_runs")).scalar_one() == "previo"
    engine.dispose()
