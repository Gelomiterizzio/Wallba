from helpers import deny_delete, policy_dict, rule

from wallba.policy.schemas import document_checksum, validate_mapping


def test_unknown_field_is_rejected_with_a_path_and_does_not_change_the_document():
    active = validate_mapping(policy_dict([deny_delete()]))
    assert active.valid and active.document is not None
    before = active.document.model_dump(mode="json")
    checksum = document_checksum(active.document)

    invalid = validate_mapping({**policy_dict([deny_delete()]), "priority": 1})

    assert invalid.valid is False
    assert invalid.document is None
    assert any(error.field == "priority" and error.code == "unknown_field" for error in invalid.errors)
    assert active.document.model_dump(mode="json") == before
    assert document_checksum(active.document) == checksum


def test_nested_unknown_field_uses_the_rule_path():
    data = policy_dict([deny_delete()])
    data["rules"][0]["priority"] = 1
    report = validate_mapping(data)
    assert report.valid is False
    assert any(error.field == "rules[0].priority" and error.code == "unknown_field" for error in report.errors)


def test_duplicate_rule_ids_negative_version_and_unknown_effect_are_rejected():
    duplicated = policy_dict([deny_delete("same-id"), deny_delete("same-id")])
    duplicate_report = validate_mapping(duplicated)
    assert duplicate_report.valid is False
    assert any(error.code == "duplicate_id" for error in duplicate_report.errors)

    negative = policy_dict([deny_delete()], version=-1)
    assert validate_mapping(negative).valid is False

    unknown = policy_dict([rule("bad-effect", "PERMIT", ["record.delete"], ["table:demo-records"])])
    assert validate_mapping(unknown).valid is False

    coerced = policy_dict([deny_delete()])
    coerced["version"] = "1"
    assert validate_mapping(coerced).valid is False

    boolean = policy_dict([deny_delete()])
    boolean["version"] = True
    assert validate_mapping(boolean).valid is False


def test_empty_rules_and_wildcard_resource_are_rejected():
    assert validate_mapping(policy_dict([])).valid is False
    wildcard = policy_dict([rule("wild", "ALLOW", ["file.read"], ["file:*"])])
    report = validate_mapping(wildcard)
    assert report.valid is False


def test_parameter_condition_must_name_one_tool_and_stay_in_range():
    multi = policy_dict(
        [
            rule(
                "mixed",
                "ALLOW",
                ["file.read", "db.query"],
                ["file:public-guide", "query:demo-records"],
                {"parameters": {"max_bytes": {"equals": 1024}}},
            )
        ]
    )
    multi_report = validate_mapping(multi)
    assert multi_report.valid is False
    assert any(error.code == "tool_parameter_mismatch" for error in multi_report.errors)

    huge = policy_dict(
        [
            rule(
                "huge-read",
                "ALLOW",
                ["file.read"],
                ["file:public-guide"],
                {"parameters": {"max_bytes": {"equals": 999999}}},
            )
        ]
    )
    huge_report = validate_mapping(huge)
    assert huge_report.valid is False
    assert any(error.code == "out_of_range" for error in huge_report.errors)


def test_real_email_and_unknown_catalog_ids_are_rejected():
    mail = policy_dict(
        [
            rule(
                "real-mail",
                "ALLOW",
                ["email.send"],
                ["mailbox:demo-outbox"],
                {"parameters": {"to": {"in": ["person@example.com"]}}},
            )
        ]
    )
    assert validate_mapping(mail).valid is False

    unknown_agent = policy_dict([rule("other", "DENY", ["record.delete"], ["table:demo-records"], agents=["other-agent"])])
    assert any(error.code == "unknown_identifier" for error in validate_mapping(unknown_agent).errors)

    critical = policy_dict(
        [
            rule(
                "critical-read",
                "ALLOW",
                ["file.read"],
                ["file:public-guide"],
                {"risk_at_most": "CRITICAL"},
            )
        ]
    )
    assert validate_mapping(critical).valid is False
