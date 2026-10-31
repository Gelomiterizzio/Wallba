"""record.delete: SQL parametrizado fijo; la tabla no viene de la solicitud."""

from __future__ import annotations

from sqlalchemy import text

from wallba.contracts.results import RecordDeleteResult
from wallba.contracts.tool_call import RecordDeleteCall
from wallba.executor.tools.base import ToolContext, ToolOutcome


def run_record_delete(call: RecordDeleteCall, context: ToolContext) -> ToolOutcome:
    deleted = context.connection.execute(
        text("DELETE FROM demo_records WHERE id = :record_id AND tenant_marker = :tenant"),
        {"record_id": call.parameters.record_id, "tenant": context.tenant_marker},
    ).rowcount
    return ToolOutcome(result=RecordDeleteResult(deleted_count=deleted), effect_count=deleted)
