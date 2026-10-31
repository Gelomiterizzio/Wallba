"""Cuatro herramientas sobre recursos sintéticos (WAL-P1-004)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from wallba.contracts.canonical import sha256_hex
from wallba.contracts.fixture_ids import target_record_id
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER
from wallba.demo.fixtures import PUBLIC_GUIDE
from wallba.executor.errors import ToolError
from wallba.executor.sandbox import Sandbox, SandboxManager
from wallba.executor.tools import TOOL_REGISTRY, ToolContext, dispatch
from wallba.foundation.database import write_transaction

RUN_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
REQUEST_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
EXECUTION_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
SEED = 7


@pytest.fixture
def sandbox(tmp_path: Path):
    manager = SandboxManager(tmp_path, "executor")
    yield manager.prepare(RUN_ID, SEED)
    manager.dispose()


def _call(tool: str, operation: str, resource_id: str, **parameters: object):
    return TOOL_CALL_ADAPTER.validate_python(
        {
            "request_id": REQUEST_ID,
            "agent_id": "demo-agent",
            "tool": tool,
            "operation": operation,
            "resource_id": resource_id,
            "parameters": parameters,
        }
    )


def _run(sandbox: Sandbox, call):
    with write_transaction(sandbox.engine) as connection:
        context = ToolContext(connection, EXECUTION_ID, sandbox.run_id, sandbox.files_dir)
        return dispatch(call, context)


def test_registry_is_closed_to_four_tools() -> None:
    assert set(TOOL_REGISTRY) == {"file.read", "email.send", "record.delete", "db.query"}


def test_file_read_public_returns_content_and_digest(sandbox: Sandbox) -> None:
    outcome = _run(sandbox, _call("file.read", "read", "file:public-guide", max_bytes=1024))
    data = PUBLIC_GUIDE.encode("utf-8")
    assert outcome.result.content == PUBLIC_GUIDE
    assert outcome.result.content_digest == sha256_hex(data)
    assert outcome.result.bytes == len(data)
    assert outcome.effect_count == 0


def test_file_read_respects_max_bytes(sandbox: Sandbox) -> None:
    outcome = _run(sandbox, _call("file.read", "read", "file:public-guide", max_bytes=10))
    assert outcome.result.bytes == 10
    assert outcome.result.content_digest == sha256_hex(PUBLIC_GUIDE.encode("utf-8")[:10])


def test_file_read_restricted_exposes_only_digest_and_length(sandbox: Sandbox) -> None:
    outcome = _run(sandbox, _call("file.read", "read", "file:restricted-ledger", max_bytes=1024))
    assert outcome.result.content is None
    assert outcome.result.bytes > 0


def test_file_read_rejects_symlink(sandbox: Sandbox, tmp_path: Path) -> None:
    secret = tmp_path / "fuera.txt"
    secret.write_text("secreto", encoding="utf-8")
    target = sandbox.files_dir / "public-guide.txt"
    target.chmod(0o666)
    target.unlink()
    try:
        os.symlink(secret, target)
    except OSError:
        pytest.skip("este sistema no permite crear symlinks sin privilegios")
    with pytest.raises(ToolError):
        _run(sandbox, _call("file.read", "read", "file:public-guide", max_bytes=1024))


def test_file_read_missing_file_is_confirmed_failure(sandbox: Sandbox) -> None:
    target = sandbox.files_dir / "public-guide.txt"
    target.chmod(0o666)
    target.unlink()
    with pytest.raises(ToolError):
        _run(sandbox, _call("file.read", "read", "file:public-guide", max_bytes=1024))


@pytest.mark.parametrize("resource_id", ["../../.env", "/etc/passwd", "file:public-guide\x00", "file:otro"])
def test_paths_never_reach_the_tool(resource_id: str) -> None:
    with pytest.raises(ValidationError):
        _call("file.read", "read", resource_id, max_bytes=1)


def test_email_send_only_writes_simulated_outbox(sandbox: Sandbox) -> None:
    outcome = _run(
        sandbox,
        _call("email.send", "send", "mailbox:demo-outbox", to="a@demo.test", subject="s", body="cuerpo"),
    )
    assert outcome.result.delivery == "SIMULATED"
    assert outcome.effect_count == 1
    with sandbox.engine.connect() as connection:
        row = connection.execute(text("SELECT * FROM outbox")).one()
    assert row.status == "SIMULATED"
    assert row.body_digest == sha256_hex(b"cuerpo")
    assert "cuerpo" not in tuple(str(value) for value in row)


def test_email_module_has_no_network_client() -> None:
    source = Path(TOOL_REGISTRY["email.send"].__code__.co_filename).read_text(encoding="utf-8")
    for forbidden in ("smtplib", "socket", "httpx", "requests"):
        assert f"import {forbidden}" not in source


def test_record_delete_removes_only_the_target(sandbox: Sandbox) -> None:
    before = sandbox.snapshot().record_count
    outcome = _run(
        sandbox,
        _call("record.delete", "delete", "table:demo-records", record_id=target_record_id(SEED)),
    )
    assert outcome.result.deleted_count == 1
    assert outcome.effect_count == 1
    assert sandbox.snapshot().record_count == before - 1


def test_record_delete_of_unknown_id_has_no_effect(sandbox: Sandbox) -> None:
    before = sandbox.snapshot().state_digest
    outcome = _run(
        sandbox,
        _call(
            "record.delete",
            "delete",
            "table:demo-records",
            record_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        ),
    )
    assert outcome.result.deleted_count == 0
    assert outcome.effect_count == 0
    assert sandbox.snapshot().state_digest == before


def test_db_query_list_applies_limit_and_column_allowlist(sandbox: Sandbox) -> None:
    outcome = _run(sandbox, _call("db.query", "query", "query:demo-records", query_id="list_records", limit=3))
    assert len(outcome.result.rows) == 3
    assert set(outcome.result.rows[0].model_dump()) == {"id", "label"}
    assert outcome.effect_count == 0


def test_db_query_count(sandbox: Sandbox) -> None:
    outcome = _run(sandbox, _call("db.query", "query", "query:demo-records", query_id="count_records", limit=1))
    assert outcome.result.count == 8
    assert outcome.result.rows is None
