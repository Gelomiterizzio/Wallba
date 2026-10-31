"""Catálogo de riesgo del servidor. El agente no puede rebajar la severidad."""

from __future__ import annotations

from wallba.policy.models import Risk, ToolName

AGENTS = frozenset({"demo-agent", "scoped-reader"})
ENVIRONMENTS = frozenset({"protected-fixture"})
ROLES = frozenset({"viewer", "operator", "approver", "policy_admin", "agent"})
QUERY_IDS = frozenset({"list_records", "count_records"})

TOOL_OPERATIONS = {
    ToolName.FILE_READ.value: "read",
    ToolName.EMAIL_SEND.value: "send",
    ToolName.RECORD_DELETE.value: "delete",
    ToolName.DB_QUERY.value: "query",
}

RESOURCES_BY_TOOL = {
    ToolName.FILE_READ.value: frozenset({"file:public-guide", "file:restricted-ledger"}),
    ToolName.EMAIL_SEND.value: frozenset({"mailbox:demo-outbox"}),
    ToolName.RECORD_DELETE.value: frozenset({"table:demo-records"}),
    ToolName.DB_QUERY.value: frozenset({"query:demo-records"}),
}

_RISK_ORDER = {
    Risk.LOW: 0,
    Risk.MEDIUM: 1,
    Risk.HIGH: 2,
    Risk.CRITICAL: 3,
}

_CATALOG: dict[tuple[str, str, str], Risk] = {
    ("file.read", "read", "file:public-guide"): Risk.LOW,
    ("file.read", "read", "file:restricted-ledger"): Risk.HIGH,
    ("email.send", "send", "mailbox:demo-outbox"): Risk.HIGH,
    ("record.delete", "delete", "table:demo-records"): Risk.HIGH,
    ("db.query", "query", "query:demo-records"): Risk.LOW,
}


def risk_rank(risk: Risk | str) -> int:
    value = risk if isinstance(risk, Risk) else Risk(risk)
    return _RISK_ORDER[value]


def higher_risk(left: Risk, right: Risk) -> Risk:
    return left if _RISK_ORDER[left] >= _RISK_ORDER[right] else right


def classify(tool: str, operation: str, resource_id: str, supplied: Risk | None) -> tuple[Risk, bool]:
    """Devuelve (severidad, conocido). Un recurso ausente del catálogo no es autorizable."""

    base = _CATALOG.get((tool, operation, resource_id))
    if base is None:
        return Risk.HIGH, False
    if supplied is None:
        return base, True
    return higher_risk(base, supplied), True
