import json
from pathlib import Path

from helpers import deny_delete, policy_dict

from wallba.policy.loader import load_policy
from wallba.policy.schemas import MAX_DOCUMENT_BYTES, document_checksum

ROOT = Path(__file__).resolve().parents[2]


def test_yaml_alias_duplicate_key_and_tag_are_invalid():
    alias = load_policy("agent: &name demo-agent\nother: *name\n", "yaml")
    assert alias.valid is False
    assert alias.errors[0].code == "alias_rejected"
    assert alias.document is None

    duplicate = (ROOT / "policies" / "invalid" / "duplicate-key.yaml").read_text(encoding="utf-8")
    parsed = load_policy(duplicate, "yaml")
    assert parsed.valid is False
    assert parsed.errors[0].code == "duplicate_key"

    tagged = load_policy("!!python/object/apply:os.system ['echo wallba-test']\n", "yaml")
    assert tagged.valid is False
    assert tagged.errors[0].code == "tag_rejected"


def test_multiple_documents_depth_size_and_floats_are_rejected():
    multi = load_policy('{"schema_version": "1"}\n---\n{"schema_version": "1"}\n', "yaml")
    assert multi.valid is False
    assert multi.errors[0].code == "multiple_documents"

    nested: object = "x"
    for _ in range(12):
        nested = {"level": nested}
    deep = load_policy(json.dumps(nested), "json")
    assert deep.valid is False
    assert deep.errors[0].code == "max_depth"

    huge = "a" * (MAX_DOCUMENT_BYTES + 1)
    oversized = load_policy(huge, "json")
    assert oversized.valid is False
    assert oversized.errors[0].code == "max_bytes"

    fractional = load_policy(json.dumps({"version": 1.5}), "json")
    assert fractional.valid is False
    assert fractional.errors[0].code == "unsupported_type"

    repeated = load_policy('{"schema_version":"1","schema_version":"1"}', "json")
    assert repeated.valid is False
    assert repeated.errors[0].code == "duplicate_key"


def test_equivalent_yaml_and_json_share_canonical_checksum():
    yaml_text = """
schema_version: "1"
policy_id: demo-policy
version: 1
rules:
  - id: deny-delete
    effect: DENY
    agents: [demo-agent]
    tools: [record.delete]
    resources: ["table:demo-records"]
"""
    json_text = json.dumps(policy_dict([deny_delete()]))
    yaml_report = load_policy(yaml_text, "yaml")
    json_report = load_policy(json_text, "json")
    assert yaml_report.valid and json_report.valid
    assert yaml_report.document is not None and json_report.document is not None
    assert document_checksum(yaml_report.document) == document_checksum(json_report.document)
    assert yaml_report.normalized_policy() == json_report.normalized_policy()


def test_overlong_string_is_rejected_before_evaluation():
    payload = json.dumps({"schema_version": "1", "note": "a" * 2049})
    report = load_policy(payload, "json")
    assert report.valid is False
    assert report.errors[0].code == "max_length"
    assert report.document is None


def test_bom_and_unknown_format_are_rejected():
    bom = load_policy(b"\xef\xbb\xbf" + b'{"schema_version":"1"}', "json")
    assert bom.valid is False
    unknown = load_policy("schema_version: '1'\n", "toml")
    assert unknown.valid is False
    assert unknown.errors[0].field == "format"
