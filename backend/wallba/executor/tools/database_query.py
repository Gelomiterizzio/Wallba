"""db.query: consultas predefinidas por query_id, con columnas permitidas fijas."""

from __future__ import annotations

from sqlalchemy import text

from wallba.contracts.results import DbQueryResult, RecordRow
from wallba.contracts.tool_call import DbQueryCall
from wallba.executor.tools.base import ToolContext, ToolOutcome

LIST_RECORDS = text(
    "SELECT id, label FROM demo_records WHERE tenant_marker = :tenant ORDER BY id LIMIT :limit"
)
COUNT_RECORDS = text("SELECT COUNT(*) FROM demo_records WHERE tenant_marker = :tenant")


def run_db_query(call: DbQueryCall, context: ToolContext) -> ToolOutcome:
    tenant = context.tenant_marker
    if call.parameters.query_id == "count_records":
        count = context.connection.execute(COUNT_RECORDS, {"tenant": tenant}).scalar_one()
        return ToolOutcome(result=DbQueryResult(rows=None, count=count), effect_count=0)

    rows = context.connection.execute(
        LIST_RECORDS, {"tenant": tenant, "limit": call.parameters.limit}
    ).all()
    result = DbQueryResult(rows=[RecordRow(id=row.id, label=row.label) for row in rows], count=len(rows))
    return ToolOutcome(result=result, effect_count=0)
