import sqlite3
import threading

from helpers import FailingAudit, FixedClock, RecordingAudit, deny_delete, policy_dict, rule

from wallba.policy.repository import (
    ActivationConflict,
    SqlitePolicyRepository,
    VersionConflict,
)
from wallba.policy.schemas import canonical_bytes, validate_mapping
from wallba.policy.service import PolicyConflict, PolicyService, PolicyUnavailable


def _document(version: int, rule_id: str = "deny-delete"):
    report = validate_mapping(policy_dict([deny_delete(rule_id)], version=version))
    assert report.document is not None
    return report.document


def _payload(version: int, rule_id: str = "deny-delete") -> bytes:
    return canonical_bytes(_document(version, rule_id))


def test_save_is_immutable_and_does_not_activate(tmp_path):
    repository = SqlitePolicyRepository(tmp_path / "policy.sqlite")
    service = PolicyService(repository, FixedClock(), RecordingAudit())
    first = service.create_version("demo-policy", _payload(1), "demo-policy-admin")
    assert first.active is False
    assert service.get_active_snapshot() is None

    try:
        service.create_version("demo-policy", _payload(1), "demo-policy-admin")
        raised = False
    except PolicyConflict as exc:
        raised = True
        assert exc.code == "CONFLICT"
    assert raised
    stored = service.get_version("demo-policy", 1)
    assert stored.summary.checksum == first.checksum
    assert stored.document.version == 1


def test_failed_audit_rolls_back_activation(tmp_path):
    repository = SqlitePolicyRepository(tmp_path / "policy.sqlite")
    audit = RecordingAudit()
    service = PolicyService(repository, FixedClock(), audit)
    service.create_version("demo-policy", _payload(1), "demo-policy-admin")
    service.activate("demo-policy", 1, None, "demo-policy-admin")
    service.create_version("demo-policy", _payload(2, "deny-delete-v2"), "demo-policy-admin")
    service._audit = FailingAudit()
    try:
        service.activate("demo-policy", 2, 1, "demo-policy-admin")
        assert False
    except PolicyUnavailable as exc:
        assert exc.code == "AUDIT_UNAVAILABLE"
    active = service.get_active_snapshot()
    assert active is not None
    assert active.document.version == 1
    historical = service.get_version("demo-policy", 1)
    assert historical.summary.checksum == active.checksum


def test_restart_keeps_history_and_active_pointer(tmp_path):
    path = tmp_path / "policy.sqlite"
    repository = SqlitePolicyRepository(path)
    service = PolicyService(repository, FixedClock(), RecordingAudit())
    service.create_version("demo-policy", _payload(1), "demo-policy-admin")
    service.create_version("demo-policy", _payload(2, "deny-other"), "demo-policy-admin")
    activated = service.activate("demo-policy", 2, None, "demo-policy-admin")
    reopened = PolicyService(SqlitePolicyRepository(path), FixedClock(), RecordingAudit())
    active = reopened.get_active_snapshot()
    assert active is not None
    assert active.checksum == activated.checksum
    assert reopened.get_version("demo-policy", 1).summary.active is False
    assert reopened.get_version("demo-policy", 2).summary.active is True
    page = reopened.list_versions(None, 50)
    assert {item.version for item in page.items} == {1, 2}


def test_concurrent_activation_allows_one_winner(tmp_path):
    repository = SqlitePolicyRepository(tmp_path / "policy.sqlite")
    service = PolicyService(repository, FixedClock(), RecordingAudit())
    service.create_version("demo-policy", _payload(1), "demo-policy-admin")
    service.create_version("demo-policy", _payload(2, "deny-next"), "demo-policy-admin")
    service.activate("demo-policy", 1, None, "demo-policy-admin")
    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        try:
            repository.activate(
                policy_id="demo-policy",
                version=2,
                expected_active_version=1,
                actor_id="demo-policy-admin",
                occurred_at="2026-10-31T16:00:00Z",
                audit=RecordingAudit(),
            )
            outcome = "ok"
        except ActivationConflict:
            outcome = "conflict"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["conflict", "ok"]
    active = repository.get_active_snapshot()
    assert active is not None
    assert active.document.version == 2
    assert service.get_version("demo-policy", 1).document.rules[0].id == "deny-delete"


def test_duplicate_save_raises_repository_conflict_without_update(tmp_path):
    repository = SqlitePolicyRepository(tmp_path / "policy.sqlite")
    document = _document(1)
    repository.save_version(document, "demo-policy-admin", "2026-10-31T16:00:00Z")
    try:
        repository.save_version(document, "demo-policy-admin", "2026-10-31T16:00:00Z")
        assert False
    except VersionConflict:
        pass
    assert repository.get_active_snapshot() is None


def test_tampered_row_is_not_served(tmp_path):
    path = tmp_path / "policy.sqlite"
    service = PolicyService(SqlitePolicyRepository(path), FixedClock(), RecordingAudit())
    service.create_version("demo-policy", _payload(1), "demo-policy-admin")
    service.activate("demo-policy", 1, None, "demo-policy-admin")
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE policy_versions SET checksum = ? WHERE version = 1", ("0" * 64,))
    reopened = PolicyService(SqlitePolicyRepository(path), FixedClock(), RecordingAudit())
    try:
        reopened.get_active_snapshot()
        assert False
    except PolicyUnavailable as exc:
        assert exc.code == "AUTHORIZATION_UNAVAILABLE"


def test_version_number_does_not_identify_another_policy(tmp_path):
    repository = SqlitePolicyRepository(tmp_path / "policy.sqlite")
    service = PolicyService(repository, FixedClock(), RecordingAudit())
    service.create_version("demo-policy", _payload(1), "demo-policy-admin")
    other = validate_mapping(policy_dict([deny_delete("deny-other")], version=1, policy_id="other-policy"))
    assert other.document is not None
    service.create_version("other-policy", canonical_bytes(other.document), "demo-policy-admin")
    service.activate("demo-policy", 1, None, "demo-policy-admin")

    try:
        service.activate("other-policy", 1, 1, "demo-policy-admin")
        raised = False
    except PolicyConflict as exc:
        raised = True
        assert exc.code == "STALE_POLICY"
    assert raised
    active = service.get_active_snapshot()
    assert active is not None
    assert active.document.policy_id == "demo-policy"
    assert active.document.version == 1

    swapped = service.activate(
        "other-policy",
        1,
        1,
        "demo-policy-admin",
        expected_active_policy_id="demo-policy",
    )
    assert swapped.document.policy_id == "other-policy"
    assert swapped.document.version == 1


def test_allow_rule_can_be_saved_for_catalog_resource():
    report = validate_mapping(
        policy_dict([rule("allow-read", "ALLOW", ["file.read"], ["file:public-guide"])])
    )
    assert report.valid
