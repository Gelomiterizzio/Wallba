from wallba.guard.runtime import GuardRuntime
from wallba.guard.shim import attempt
from wallba.guard.policy import decide


def test_blocked_write_does_not_change_bytes(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "notes.txt"
    target.write_bytes(b"original")
    result = attempt(root, target, "block_write", "write", apply=True, content=b"cambiado")
    assert result["outcome"] == "blocked"
    assert result["preventive"] is True
    assert result["intact"] is True
    assert target.read_bytes() == b"original"
    assert decide("block_write", "write").preventive is True


def test_monitor_write_is_observed_and_applied(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "notes.txt"
    target.write_bytes(b"original")
    result = attempt(root, target, "monitor", "write", apply=True, content=b"nuevo")
    assert result["outcome"] == "observed"
    assert result["preventive"] is False
    assert target.read_bytes() == b"nuevo"


def test_runtime_records_the_instrumented_agent_only(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "notes.txt").write_text("original", encoding="utf-8")
    state = tmp_path / "state"
    runtime = GuardRuntime(state / "guard.sqlite", state)
    opened = runtime.open_project(str(root))
    project_id = opened["project"]["id"]
    runtime.protect(project_id, "notes.txt", "file", "block_all")
    probed = runtime.probe(project_id, "notes.txt", "read", apply=False, content=None)
    assert probed["outcome"] == "blocked"
    assert probed["origin_detail"] == "wallba-test-agent"
    event = next(item for item in runtime.events(project_id) if item["operation"] == "read")
    assert "original" not in event["explanation"]
    assert event["origin_detail"] == "wallba-test-agent"
