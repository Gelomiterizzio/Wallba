"""Hook del agente instrumentado. No modifica la configuración de Claude Code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from wallba.guard.policy import Decision, decide

SNIPPET = """\
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Write|Edit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python -m wallba.guard.hook"
          }
        ]
      }
    ]
  }
}
"""
FILE_TOOLS = frozenset({"Read", "Write", "Edit", "NotebookEdit"})
UNDETERMINED = "ORIGEN NO DETERMINADO"


@dataclass(frozen=True)
class HookResult:
    exit_code: int
    message: str
    decision: Decision


def snippet() -> str:
    """Texto para que una persona lo instale. Esta función no escribe archivos."""
    return SNIPPET


def tool_operation(tool_name: str) -> str | None:
    if tool_name == "Read":
        return "read"
    if tool_name in {"Write", "Edit", "NotebookEdit"}:
        return "write"
    return None


def evaluate_payload(payload: dict, posture_for) -> HookResult:
    tool_name = str(payload.get("tool_name") or "")
    operation = tool_operation(tool_name)
    if operation is None:
        decision = Decision("ALLOW", False, False, None, "La herramienta no es una operación de archivo cubierta por el hook.")
        return HookResult(0, decision.reason, decision)
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    raw_path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
    if not isinstance(raw_path, str) or not raw_path:
        decision = Decision("DENY", True, True, None, "No se identificó la ruta. Se deniega antes de ejecutar.")
        return HookResult(2, decision.reason, decision)
    posture = posture_for(raw_path, operation)
    decision = decide(posture, operation)
    if decision.effect == "DENY":
        return HookResult(2, decision.reason, decision)
    return HookResult(0, decision.reason, decision)


def main() -> int:
    import sys

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("La entrada del hook no es JSON. Se deniega.")
        return 2
    db = Path(sys.environ["WALLBA_GUARD_DB"]) if sys.environ.get("WALLBA_GUARD_DB") else None

    def posture_for(raw_path: str, _operation: str) -> str | None:
        if db is None or not db.is_file():
            return None
        from wallba.guard.runtime import posture_for_filesystem_path

        return posture_for_filesystem_path(db, raw_path)

    result = evaluate_payload(payload if isinstance(payload, dict) else {}, posture_for)
    print(result.message)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
