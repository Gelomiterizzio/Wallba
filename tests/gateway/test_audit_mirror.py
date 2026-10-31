from pathlib import Path

from sqlalchemy import text

from wallba.foundation.database import create_sqlite_engine, run_migrations, write_transaction
from wallba.gateway.audit import TransactionalOutbox


def test_gateway_event_is_visible_to_the_dashboard_chain(tmp_path: Path):
    database = tmp_path / "control.sqlite"
    run_migrations(database)
    engine = create_sqlite_engine(database)
    outbox = TransactionalOutbox()
    with write_transaction(engine) as connection:
        outbox.append(
            {
                "event_type": "authorization_decided",
                "request_id": "11111111-1111-4111-8111-111111111111",
                "run_id": "33333333-3333-4333-8333-333333333333",
                "principal_id": "demo-operator",
                "decision": "DENY",
                "risk": "HIGH",
                "reason_code": "DENY_RULE",
                "policy_id": "demo-policy",
                "policy_version": 1,
            },
            connection,
        )
    with engine.connect() as connection:
        count = connection.execute(text("SELECT COUNT(*) FROM audit_events")).scalar_one()
        outbox_count = connection.execute(text("SELECT COUNT(*) FROM p3_audit_outbox")).scalar_one()
    assert count == 1
    assert outbox_count == 1
