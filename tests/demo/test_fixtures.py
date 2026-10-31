"""Fixtures duales y catálogo de escenarios (WAL-P1-007)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from wallba.demo.fixtures import build_fixture, fixture_digest
from wallba.demo.scenarios import SCENARIOS, SCENARIOS_BY_ID
from wallba.executor.sandbox import SandboxError, SandboxManager

RUN_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_RUN = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


@pytest.fixture
def managers(tmp_path: Path):
    baseline = SandboxManager(tmp_path / "baseline", "baseline")
    protected = SandboxManager(tmp_path / "protected", "executor")
    yield baseline, protected
    baseline.dispose()
    protected.dispose()


def test_same_seed_gives_same_fixture() -> None:
    assert fixture_digest(build_fixture(7)) == fixture_digest(build_fixture(7))


def test_different_seed_gives_different_fixture() -> None:
    assert fixture_digest(build_fixture(7)) != fixture_digest(build_fixture(8))


def test_both_sides_start_equal_but_in_separate_volumes(managers) -> None:
    baseline, protected = managers
    left = baseline.prepare(RUN_ID, 7)
    right = protected.prepare(RUN_ID, 7)
    assert left.snapshot().state_digest == right.snapshot().state_digest
    assert left.fixture_digest == right.fixture_digest
    assert left.path != right.path
    with left.engine.begin() as connection:
        connection.execute(text("DELETE FROM demo_records"))
    assert left.snapshot().state_digest != right.snapshot().state_digest
    assert right.snapshot().record_count == 8


def test_fixture_starts_with_empty_outbox_and_journal(managers) -> None:
    snapshot = managers[0].prepare(RUN_ID, 7).snapshot()
    assert snapshot.record_count == 8
    assert snapshot.outbox_count == 0
    assert snapshot.journal_count == 0


def test_prepare_refuses_to_overwrite_existing_run(managers) -> None:
    baseline, _ = managers
    baseline.prepare(RUN_ID, 7)
    with pytest.raises(SandboxError):
        baseline.prepare(RUN_ID, 7)


@pytest.mark.parametrize("bad", ["../fuera", "..", "/etc", "C:\\Windows", "no-uuid", f"{RUN_ID}/../.."])
def test_path_escape_is_rejected(managers, bad: str) -> None:
    baseline, _ = managers
    with pytest.raises(SandboxError):
        baseline.reset(bad)
    with pytest.raises(SandboxError):
        baseline.prepare(bad, 1)


def test_reset_deletes_only_its_own_labeled_directory(managers, tmp_path: Path) -> None:
    baseline, _ = managers
    keep = baseline.prepare(OTHER_RUN, 7)
    gone = baseline.prepare(RUN_ID, 7)
    baseline.reset(RUN_ID)
    assert not gone.path.exists()
    assert keep.path.exists()


def test_reset_refuses_unlabeled_directory(managers, tmp_path: Path) -> None:
    baseline, _ = managers
    baseline.prepare(OTHER_RUN, 7)
    foreign = tmp_path / "baseline" / RUN_ID
    foreign.mkdir()
    (foreign / "documento-personal.txt").write_text("no borrar", encoding="utf-8")
    with pytest.raises(SandboxError):
        baseline.reset(RUN_ID)
    assert (foreign / "documento-personal.txt").exists()


def test_catalog_has_ten_scenarios_labeled_as_expectations() -> None:
    assert [scenario.id for scenario in SCENARIOS] == [f"S{index:02d}" for index in range(1, 11)]
    for scenario in SCENARIOS:
        assert scenario.view().expectation.label == "EXPECTATION"


def test_special_sequences_are_declared() -> None:
    assert SCENARIOS_BY_ID["S07"].baseline_plan == "altered_body"
    assert SCENARIOS_BY_ID["S10"].baseline_plan == "repeat_twice"
    assert SCENARIOS_BY_ID["S09"].baseline_plan == "not_applicable"
    assert SCENARIOS_BY_ID["S09"].tool is None
