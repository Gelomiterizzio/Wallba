from pathlib import Path

from helpers import RECORD_ID, context, email, request_for

from wallba.policy.evaluator import evaluate
from wallba.policy.loader import load_policy
from wallba.policy.models import Decision, ReasonCode, Risk
from wallba.policy.schemas import document_checksum, snapshot_from_document

ROOT = Path(__file__).resolve().parents[2]

CASES = (
    ("S01", "file.read", "file:public-guide", {"max_bytes": 1024}, Decision.ALLOW, ReasonCode.RULE_ALLOW, Risk.LOW, ("allow-public-read",)),
    ("S02", "file.read", "file:restricted-ledger", {"max_bytes": 1024}, Decision.DENY, ReasonCode.DEFAULT_DENY, Risk.HIGH, ()),
    ("S03", "db.query", "query:demo-records", {"query_id": "list_records", "limit": 10}, Decision.ALLOW, ReasonCode.RULE_ALLOW, Risk.LOW, ("allow-demo-query",)),
    ("S04", "record.delete", "table:demo-records", {"record_id": RECORD_ID}, Decision.DENY, ReasonCode.RULE_DENY, Risk.HIGH, ("deny-delete",)),
    ("S05", "email.send", "mailbox:demo-outbox", email("outside@external.test"), Decision.DENY, ReasonCode.DEFAULT_DENY, Risk.HIGH, ()),
    ("S06", "email.send", "mailbox:demo-outbox", email("reviewer@example.test"), Decision.REQUIRE_APPROVAL, ReasonCode.APPROVAL_REQUIRED, Risk.HIGH, ("approve-internal-email",)),
    ("S08", "record.delete", "table:demo-records", {"record_id": RECORD_ID}, Decision.DENY, ReasonCode.RULE_DENY, Risk.HIGH, ("deny-delete",)),
)


def _snapshots():
    yaml_report = load_policy((ROOT / "policies" / "demo.yaml").read_text(encoding="utf-8"), "yaml")
    json_report = load_policy((ROOT / "policies" / "demo.json").read_text(encoding="utf-8"), "json")
    assert yaml_report.document is not None and json_report.document is not None
    assert document_checksum(yaml_report.document) == document_checksum(json_report.document)
    return snapshot_from_document(yaml_report.document), snapshot_from_document(json_report.document)


def test_demo_yaml_and_json_produce_the_same_decisions():
    yaml_snapshot, json_snapshot = _snapshots()
    trusted = context()
    for name, tool, resource, parameters, decision, reason, risk, matched in CASES:
        request = request_for(tool, resource, parameters)
        from_yaml = evaluate(request, trusted, yaml_snapshot)
        from_json = evaluate(request, trusted, json_snapshot)
        assert from_yaml == from_json, name
        assert from_yaml.decision is decision, name
        assert from_yaml.reason_code is reason, name
        assert from_yaml.risk is risk, name
        assert tuple(from_yaml.matched_rule_ids) == matched, name
        assert from_yaml.policy_id == "demo-policy"
        assert from_yaml.policy_version == 1


def test_invalid_fixture_is_not_activable():
    text = (ROOT / "policies" / "invalid" / "duplicate-key.yaml").read_text(encoding="utf-8")
    report = load_policy(text, "yaml")
    assert report.valid is False
    assert report.document is None
    assert report.errors[0].code == "duplicate_key"
