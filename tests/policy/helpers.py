from __future__ import annotations

from datetime import datetime, timezone

from wallba.policy.models import EvaluationRequest, Risk, TrustedContext
from wallba.policy.repository import AuditFailure

REQUEST_ID = "11111111-1111-4111-8111-111111111111"
RECORD_ID = "22222222-2222-4222-8222-222222222222"
WHEN = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)

_OPERATIONS = {
    "file.read": "read",
    "email.send": "send",
    "record.delete": "delete",
    "db.query": "query",
}


class FixedClock:
    def __init__(self, instant: datetime = WHEN) -> None:
        self.instant = instant

    def now(self) -> datetime:
        return self.instant


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def append(self, event: dict[str, object], connection: object) -> None:
        if connection is None:
            raise AuditFailure()
        self.events.append(dict(event))


class FailingAudit:
    def append(self, event: dict[str, object], connection: object) -> None:
        raise AuditFailure()


def policy_dict(rules: list[dict[str, object]], version: int = 1, policy_id: str = "demo-policy") -> dict[str, object]:
    return {
        "schema_version": "1",
        "policy_id": policy_id,
        "version": version,
        "rules": rules,
    }


def rule(
    rule_id: str,
    effect: str,
    tools: list[str],
    resources: list[str],
    conditions: dict[str, object] | None = None,
    agents: list[str] | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "id": rule_id,
        "effect": effect,
        "agents": agents or ["demo-agent"],
        "tools": tools,
        "resources": resources,
    }
    if conditions is not None:
        data["conditions"] = conditions
    return data


def deny_delete(rule_id: str = "deny-delete") -> dict[str, object]:
    return rule(rule_id, "DENY", ["record.delete"], ["table:demo-records"])


def request_for(
    tool: str,
    resource_id: str,
    parameters: dict[str, object],
    agent_id: str = "demo-agent",
    operation: str | None = None,
    request_id: str = REQUEST_ID,
) -> EvaluationRequest:
    return EvaluationRequest(
        request_id=request_id,
        agent_id=agent_id,
        tool=tool,
        operation=operation or _OPERATIONS[tool],
        resource_id=resource_id,
        parameters=parameters,
    )


def context(
    agent_id: str = "demo-agent",
    roles: list[str] | None = None,
    environment_id: str = "protected-fixture",
    risk: Risk | None = None,
    server_time: datetime = WHEN,
) -> TrustedContext:
    return TrustedContext(
        principal_id="demo-operator",
        agent_id=agent_id,
        roles=["agent"] if roles is None else roles,
        environment_id=environment_id,
        server_time=server_time,
        resource_version="1",
        risk=risk,
    )


def email(to: str, body: str = "aviso") -> dict[str, object]:
    return {"to": to, "subject": "aviso", "body": body}
