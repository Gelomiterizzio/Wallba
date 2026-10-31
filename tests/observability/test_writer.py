"""Escritura, redacción, cadena y concurrencia de la auditoría (WAL-P4-003)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from wallba.contracts.ports import AuditEventDraft
from wallba.foundation.database import create_sqlite_engine, run_migrations, write_transaction
from wallba.observability.adapters import PolicyAuditSink
from wallba.observability.ports import AuditSchemaError
from wallba.observability.redaction import REDACTED, safe_event_fields
from wallba.observability.writer import GENESIS_HASH, AuditWriter, verify_chain
from wallba.policy.repository import AuditFailure

REQUEST = "11111111-1111-4111-8111-111111111111"
SECRET = "super-secreto-del-fixture"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.sqlite"
    run_migrations(path)
    return path


@pytest.fixture
def engine(db_path: Path):
    value = create_sqlite_engine(db_path)
    yield value
    value.dispose()


def _append(engine, writer: AuditWriter | None = None, **fields) -> str:
    draft = AuditEventDraft(event_type="authorization_decided", **fields)
    with write_transaction(engine) as connection:
        return (writer or AuditWriter()).append(draft, connection)


def _all_raw(engine) -> str:
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT * FROM audit_events")).all()
    return " ".join(str(value) for row in rows for value in row)


class TestRedaction:
    def test_unknown_fields_never_reach_the_event(self) -> None:
        safe = safe_event_fields(
            {
                "event_type": "request_received",
                "body": SECRET,
                "token": SECRET,
                "password": SECRET,
                "path": f"/home/{SECRET}",
                "nested": {"secret": SECRET},
            }
        )
        assert safe == {"event_type": "request_received"}

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("principal_id", "persona@empresa.com"),
            ("agent_id", "Bearer abc123"),
            ("resource_id", "../../etc/passwd"),
            ("resource_id", "/data/control.sqlite"),
            ("reason_code", f"token={SECRET}"),
            ("policy_id", "<script>alert(1)</script>"),
            ("principal_id", 123),
        ],
    )
    def test_value_outside_field_format_is_redacted(self, field: str, value: object) -> None:
        assert safe_event_fields({"event_type": "demo_started", field: value})[field] == REDACTED

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("event_type", "inventado"),
            ("request_id", "no-es-uuid"),
            ("run_id", SECRET),
            ("request_digest", "sha256-fixture"),
            ("decision", "MAYBE"),
            ("risk", "SAFE"),
            ("tool", "shell.exec"),
            ("policy_version", 0),
            ("policy_version", True),
        ],
    )
    def test_invalid_typed_field_rejects_the_event(self, field: str, value: object) -> None:
        with pytest.raises(AuditSchemaError):
            safe_event_fields({"event_type": "demo_started", field: value})

    def test_nulls_are_omitted_not_filled(self) -> None:
        safe = safe_event_fields({"event_type": "policy_activated", "request_id": None, "request_digest": None})
        assert safe == {"event_type": "policy_activated"}


class TestChain:
    def test_first_event_uses_documented_root(self, engine) -> None:
        _append(engine)
        with engine.connect() as connection:
            row = connection.execute(text("SELECT sequence, previous_hash FROM audit_events")).one()
        assert row.sequence == 1
        assert row.previous_hash == GENESIS_HASH

    def test_chain_links_and_verifies(self, engine) -> None:
        for _ in range(5):
            _append(engine, request_id=REQUEST, decision="DENY", risk="HIGH")
        with engine.connect() as connection:
            report = verify_chain(connection)
            rows = connection.execute(
                text("SELECT sequence, previous_hash, event_hash FROM audit_events ORDER BY sequence")
            ).all()
        assert report.valid and report.checked == 5
        assert [r.sequence for r in rows] == [1, 2, 3, 4, 5]
        assert all(rows[i].previous_hash == rows[i - 1].event_hash for i in range(1, 5))

    def test_empty_chain_is_valid(self, engine) -> None:
        with engine.connect() as connection:
            assert verify_chain(connection).valid

    def test_update_and_delete_are_blocked_by_the_database(self, engine) -> None:
        _append(engine)
        for statement in ("UPDATE audit_events SET decision = 'ALLOW'", "DELETE FROM audit_events"):
            with pytest.raises(DBAPIError), write_transaction(engine) as connection:
                connection.execute(text(statement))

    @pytest.mark.parametrize(
        "tamper",
        [
            "UPDATE audit_events SET decision = 'ALLOW' WHERE sequence = 2",
            "UPDATE audit_events SET fields_json = replace(fields_json, 'DENY', 'ALLOW') WHERE sequence = 2",
            "UPDATE audit_events SET event_hash = 'ffff' WHERE sequence = 2",
            "DELETE FROM audit_events WHERE sequence = 2",
        ],
    )
    def test_tampering_after_removing_triggers_is_detected(self, engine, tamper: str) -> None:
        for _ in range(3):
            _append(engine, decision="DENY")
        with write_transaction(engine) as connection:
            connection.execute(text("DROP TRIGGER audit_events_no_update"))
            connection.execute(text("DROP TRIGGER audit_events_no_delete"))
            connection.execute(text(tamper))
        with engine.connect() as connection:
            report = verify_chain(connection)
        assert not report.valid
        assert report.first_invalid_sequence in {2, 3}


class TestTransactions:
    def test_event_rolls_back_with_the_producer(self, engine) -> None:
        with pytest.raises(RuntimeError), write_transaction(engine) as connection:
            AuditWriter().append(AuditEventDraft(event_type="demo_started"), connection)
            raise RuntimeError("fallo del productor")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM audit_events")).scalar_one() == 0

    def test_concurrent_producers_do_not_repeat_sequences(self, engine) -> None:
        barrier = threading.Barrier(4)
        errors: list[Exception] = []

        def worker() -> None:
            barrier.wait()
            try:
                for _ in range(10):
                    _append(engine, decision="DENY")
            except Exception as exc:  # noqa: BLE001 - la prueba informa cualquier fallo
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        with engine.connect() as connection:
            report = verify_chain(connection)
            sequences = connection.execute(text("SELECT sequence FROM audit_events")).scalars().all()
        assert report.valid and report.checked == 40
        assert sorted(sequences) == list(range(1, 41))

    def test_unique_sequence_is_the_last_defense(self, engine) -> None:
        _append(engine)
        with pytest.raises(IntegrityError), write_transaction(engine) as connection:
            connection.execute(
                text(
                    "INSERT INTO audit_events (event_id, sequence, event_type, occurred_at, fields_json, "
                    "previous_hash, event_hash) VALUES ('x', 1, 'demo_started', 't', '{}', 'p', 'h')"
                )
            )

    def test_raw_sqlite_connection_shares_the_same_chain(self, db_path: Path, engine) -> None:
        _append(engine)
        con = sqlite3.connect(db_path, isolation_level=None)
        con.execute("BEGIN IMMEDIATE")
        AuditWriter().append(
            {
                "event_type": "policy_activated",
                "policy_id": "demo-policy",
                "policy_version": 1,
                "checksum": "a" * 64,
                "actor_id": "demo-policy-admin",
                "occurred_at": "1999-01-01T00:00:00Z",
            },
            con,
        )
        con.execute("COMMIT")
        con.close()
        with engine.connect() as connection:
            report = verify_chain(connection)
            row = connection.execute(
                text("SELECT principal_id, occurred_at FROM audit_events WHERE sequence = 2")
            ).one()
        assert report.valid and report.checked == 2
        assert row.principal_id == "demo-policy-admin"
        # La hora la fija el servidor, no el borrador.
        assert not row.occurred_at.startswith("1999")

    def test_unsupported_transaction_fails_closed(self) -> None:
        with pytest.raises(RuntimeError):
            AuditWriter().append(AuditEventDraft(event_type="demo_started"), object())


def test_no_secret_reaches_storage(engine) -> None:
    with write_transaction(engine) as connection:
        AuditWriter().append(
            {
                "event_type": "authorization_decided",
                "principal_id": f"x {SECRET}",
                "reason_code": SECRET,
                "body": SECRET,
                "authorization": f"Bearer {SECRET}",
            },
            connection,
        )
    assert SECRET not in _all_raw(engine)


def test_policy_adapter_maps_any_failure_to_audit_failure() -> None:
    with pytest.raises(AuditFailure):
        PolicyAuditSink(AuditWriter()).append({"event_type": "inventado"}, object())
