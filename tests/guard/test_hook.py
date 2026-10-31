import json
from pathlib import Path

from wallba.guard.hook import evaluate_payload, snippet
from wallba.guard.runtime import GuardRuntime


def test_snippet_is_text_and_does_not_write_claude_config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    text = snippet()
    parsed = json.loads(text)
    assert parsed["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "python -m wallba.guard.hook"
    assert not (home / ".claude").exists()


def test_missing_path_on_a_file_tool_is_denied():
    result = evaluate_payload({"tool_name": "Read", "tool_input": {}}, lambda _path, _op: None)
    assert result.exit_code == 2
    assert result.decision.preventive is True


def test_hook_denies_a_protected_write_without_touching_the_file(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "notes.txt"
    target.write_text("original", encoding="utf-8")
    state = tmp_path / "state"
    runtime = GuardRuntime(state / "guard.sqlite", state)
    opened = runtime.open_project(str(root))
    runtime.protect(opened["project"]["id"], "notes.txt", "file", "block_write")

    def posture_for(raw_path: str, _operation: str) -> str | None:
        if Path(raw_path).resolve() == target.resolve():
            return "block_write"
        return None

    result = evaluate_payload(
        {"tool_name": "Write", "tool_input": {"file_path": str(target)}},
        posture_for,
    )
    assert result.exit_code == 2
    assert target.read_text(encoding="utf-8") == "original"
