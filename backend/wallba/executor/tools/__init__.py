"""Registro cerrado de herramientas: sin imports dinámicos desde el payload."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from wallba.contracts.tool_call import ToolCall
from wallba.executor.tools.base import ToolContext, ToolOutcome
from wallba.executor.tools.database_query import run_db_query
from wallba.executor.tools.email_sender import run_email_send
from wallba.executor.tools.file_reader import run_file_read
from wallba.executor.tools.record_deleter import run_record_delete

TOOL_REGISTRY: dict[str, Callable[[Any, ToolContext], ToolOutcome]] = {
    "file.read": run_file_read,
    "email.send": run_email_send,
    "record.delete": run_record_delete,
    "db.query": run_db_query,
}


def dispatch(call: ToolCall, context: ToolContext) -> ToolOutcome:
    return TOOL_REGISTRY[call.tool](call, context)


__all__ = ["TOOL_REGISTRY", "ToolContext", "ToolOutcome", "dispatch"]
