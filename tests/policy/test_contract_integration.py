from helpers import context, email, policy_dict, request_for, rule

from wallba.policy.evaluator import evaluate, policy_binding, same_policy_binding
from wallba.policy.models import Decision, ReasonCode
from wallba.policy.schemas import snapshot_from_document, validate_mapping


def _snapshot(effect: str, version: int):
    data = policy_dict(
        [
            rule(
                "mail-rule",
                effect,
                ["email.send"],
                ["mailbox:demo-outbox"],
                {"parameters": {"to": {"in": ["reviewer@example.test"]}}},
            )
        ],
        version=version,
    )
    report = validate_mapping(data)
    assert report.document is not None
    return snapshot_from_document(report.document)


def test_old_approval_binding_does_not_match_a_new_snapshot():
    approved = _snapshot("REQUIRE_APPROVAL", 1)
    denied = _snapshot("DENY", 2)
    request = request_for("email.send", "mailbox:demo-outbox", email("reviewer@example.test"))
    trusted = context()
    first = evaluate(request, trusted, approved)
    second = evaluate(request, trusted, denied)
    assert first.decision is Decision.REQUIRE_APPROVAL
    assert first.reason_code is ReasonCode.APPROVAL_REQUIRED
    assert second.decision is Decision.DENY
    assert second.reason_code is ReasonCode.RULE_DENY
    binding = policy_binding(approved)
    assert same_policy_binding(binding, approved)
    assert same_policy_binding(binding, denied) is False
    assert "approval_id" not in evaluate.__code__.co_varnames


def test_self_asserted_approval_field_does_not_allow():
    snapshot = _snapshot("DENY", 1)
    request = request_for("email.send", "mailbox:demo-outbox", email("reviewer@example.test")).model_dump(mode="json")
    request["approved"] = True
    result = evaluate(request, context(), snapshot)
    assert result.decision is Decision.DENY
    assert result.reason_code is not ReasonCode.RULE_ALLOW
