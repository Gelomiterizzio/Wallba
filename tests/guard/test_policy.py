from wallba.guard.policy import decide


def test_unknown_posture_denies_before_execution():
    decision = decide("invented", "read")
    assert decision.effect == "DENY"
    assert decision.preventive is True


def test_monitor_allows_and_is_not_preventive():
    decision = decide("monitor", "write")
    assert decision.effect == "ALLOW"
    assert decision.preventive is False
    assert decision.covered is True


def test_block_write_does_not_deny_read():
    assert decide("block_write", "read").effect == "ALLOW"
    denied = decide("block_write", "write")
    assert denied.effect == "DENY"
    assert denied.preventive is True


def test_uncovered_path_is_not_described_as_blocked():
    decision = decide(None, "read")
    assert decision.effect == "ALLOW"
    assert decision.covered is False
    assert decision.preventive is False
