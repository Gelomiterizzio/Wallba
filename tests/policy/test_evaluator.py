import itertools
from datetime import timedelta

from helpers import WHEN, context, deny_delete, policy_dict, request_for, rule

from wallba.policy.evaluator import evaluate
from wallba.policy.models import Decision, ReasonCode, Risk
from wallba.policy.schemas import document_checksum, snapshot_from_document, validate_mapping


def _snapshot(rules: list[dict[str, object]], version: int = 1):
    report = validate_mapping(policy_dict(rules, version=version))
    assert report.valid and report.document is not None
    return snapshot_from_document(report.document)


def _read():
    return request_for("file.read", "file:public-guide", {"max_bytes": 1024})


def test_deny_wins_over_allow_and_approval_in_every_order():
    base = [
        rule("allow-read", "ALLOW", ["file.read"], ["file:public-guide"]),
        rule("deny-read", "DENY", ["file.read"], ["file:public-guide"]),
        rule("approve-read", "REQUIRE_APPROVAL", ["file.read"], ["file:public-guide"]),
    ]
    signatures = set()
    checksums = set()
    for ordered in itertools.permutations(base):
        snapshot = _snapshot(list(ordered))
        result = evaluate(_read(), context(), snapshot)
        signatures.add((result.decision, result.reason_code, tuple(result.matched_rule_ids), result.risk))
        checksums.add(snapshot.checksum)
    assert signatures == {
        (Decision.DENY, ReasonCode.RULE_DENY, ("allow-read", "approve-read", "deny-read"), Risk.LOW)
    }
    assert len(checksums) > 1


def test_missing_invalid_and_digest_mismatch_fail_closed():
    missing = evaluate(_read(), context(), None)
    assert missing.decision is Decision.DENY
    assert missing.reason_code is ReasonCode.POLICY_MISSING
    assert missing.policy_id is None
    assert missing.risk is Risk.LOW

    snapshot = _snapshot([deny_delete()])
    tampered = snapshot.model_copy(update={"checksum": "0" * 64})
    mismatch = evaluate(
        request_for("record.delete", "table:demo-records", {"record_id": "22222222-2222-4222-8222-222222222222"}),
        context(),
        tampered,
    )
    assert mismatch.decision is Decision.DENY
    assert mismatch.reason_code is ReasonCode.DIGEST_MISMATCH
    assert mismatch.risk is Risk.CRITICAL

    broken = {"snapshot": True}
    unavailable = evaluate(_read(), context(), broken)  # type: ignore[arg-type]
    assert unavailable.decision is Decision.DENY
    assert unavailable.reason_code is ReasonCode.AUTHORIZATION_UNAVAILABLE


def test_server_time_and_repetition_do_not_change_the_decision():
    snapshot = _snapshot([rule("allow-read", "ALLOW", ["file.read"], ["file:public-guide"])])
    later = context(server_time=WHEN + timedelta(hours=5))
    first = evaluate(_read(), context(), snapshot)
    second = evaluate(_read(), later, snapshot)
    assert first == second
    assert first.decision is Decision.ALLOW
    assert first.reason_code is ReasonCode.RULE_ALLOW
    assert document_checksum(snapshot.document) == snapshot.checksum


def test_no_matching_rule_is_default_deny_and_agent_mismatch_does_not_allow():
    snapshot = _snapshot([deny_delete()])
    result = evaluate(_read(), context(), snapshot)
    assert result.decision is Decision.DENY
    assert result.reason_code is ReasonCode.DEFAULT_DENY
    assert result.matched_rule_ids == []
    assert result.policy_id == "demo-policy"

    spoofed = evaluate(_read(), context(agent_id="scoped-reader"), snapshot)
    assert spoofed.decision is Decision.DENY
    assert spoofed.reason_code is ReasonCode.DEFAULT_DENY


def test_critical_supplied_risk_cannot_authorize():
    snapshot = _snapshot([rule("allow-read", "ALLOW", ["file.read"], ["file:public-guide"])])
    result = evaluate(_read(), context(risk=Risk.CRITICAL), snapshot)
    assert result.decision is Decision.DENY
    assert result.risk is Risk.CRITICAL
    assert result.reason_code is not ReasonCode.RULE_ALLOW
