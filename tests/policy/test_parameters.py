from helpers import RECORD_ID, context, email, policy_dict, request_for, rule

from wallba.policy.evaluator import evaluate
from wallba.policy.models import Decision, ReasonCode, Risk
from wallba.policy.schemas import snapshot_from_document, validate_mapping


def _snapshot(rules: list[dict[str, object]]):
    report = validate_mapping(policy_dict(rules))
    assert report.valid and report.document is not None
    return snapshot_from_document(report.document)


def test_recipient_outside_the_list_and_unknown_query_are_denied():
    snapshot = _snapshot(
        [
            rule(
                "approve-internal-email",
                "REQUIRE_APPROVAL",
                ["email.send"],
                ["mailbox:demo-outbox"],
                {"parameters": {"to": {"in": ["reviewer@example.test"]}}},
            ),
            rule(
                "allow-list",
                "ALLOW",
                ["db.query"],
                ["query:demo-records"],
                {"parameters": {"query_id": {"in": ["list_records"]}}},
            ),
        ]
    )
    outside = evaluate(
        request_for("email.send", "mailbox:demo-outbox", email("outside@external.test")),
        context(),
        snapshot,
    )
    assert outside.decision is Decision.DENY
    assert outside.reason_code is ReasonCode.DEFAULT_DENY

    listed = evaluate(
        request_for("email.send", "mailbox:demo-outbox", email("Reviewer@Example.Test")),
        context(),
        snapshot,
    )
    assert listed.decision is Decision.REQUIRE_APPROVAL
    assert listed.matched_rule_ids == ["approve-internal-email"]

    unknown_query = evaluate(
        request_for("db.query", "query:demo-records", {"query_id": "drop_table", "limit": 10}),
        context(),
        snapshot,
    )
    assert unknown_query.decision is Decision.DENY
    assert unknown_query.reason_code is not ReasonCode.RULE_ALLOW

    other_query = evaluate(
        request_for("db.query", "query:demo-records", {"query_id": "count_records", "limit": 10}),
        context(),
        snapshot,
    )
    assert other_query.decision is Decision.DENY
    assert other_query.reason_code is ReasonCode.DEFAULT_DENY


def test_omitted_coerced_and_extra_parameters_are_denied():
    snapshot = _snapshot([rule("allow-read", "ALLOW", ["file.read"], ["file:public-guide"])])
    omitted = evaluate(request_for("file.read", "file:public-guide", {}), context(), snapshot)
    coerced = evaluate(
        request_for("file.read", "file:public-guide", {"max_bytes": "1024"}),
        context(),
        snapshot,
    )
    boolean = evaluate(
        request_for("file.read", "file:public-guide", {"max_bytes": True}),
        context(),
        snapshot,
    )
    extra = evaluate(
        request_for("file.read", "file:public-guide", {"max_bytes": 1024, "path": "../ledger"}),
        context(),
        snapshot,
    )
    for result in (omitted, coerced, boolean, extra):
        assert result.decision is Decision.DENY
        assert result.reason_code is not ReasonCode.RULE_ALLOW


def test_agent_cannot_lower_risk_of_delete():
    snapshot = _snapshot(
        [
            rule(
                "allow-low-delete",
                "ALLOW",
                ["record.delete"],
                ["table:demo-records"],
                {"risk_at_most": "LOW"},
            )
        ]
    )
    result = evaluate(
        request_for("record.delete", "table:demo-records", {"record_id": RECORD_ID}),
        context(risk=Risk.LOW),
        snapshot,
    )
    assert result.decision is Decision.DENY
    assert result.risk is Risk.HIGH
    assert result.reason_code is ReasonCode.DEFAULT_DENY


def test_exact_max_bytes_condition_limits_the_allow():
    snapshot = _snapshot(
        [
            rule(
                "exact-read",
                "ALLOW",
                ["file.read"],
                ["file:public-guide"],
                {"parameters": {"max_bytes": {"equals": 1024}}},
            )
        ]
    )
    allowed = evaluate(request_for("file.read", "file:public-guide", {"max_bytes": 1024}), context(), snapshot)
    larger = evaluate(request_for("file.read", "file:public-guide", {"max_bytes": 2048}), context(), snapshot)
    assert allowed.decision is Decision.ALLOW
    assert larger.decision is Decision.DENY
    assert larger.reason_code is ReasonCode.DEFAULT_DENY
