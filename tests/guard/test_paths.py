from pathlib import Path

import pytest

from wallba.guard.errors import GuardError
from wallba.guard.paths import assert_separated, canonical_directory, relative_parts, resolve_inside


def test_rejects_parent_segments_and_relative_roots(tmp_path):
    with pytest.raises(GuardError) as caught:
        relative_parts("../secret")
    assert caught.value.code == "PATH_INVALID"
    with pytest.raises(GuardError) as relative:
        canonical_directory("proyecto")
    assert relative.value.code == "PATH_NOT_ABSOLUTE"
    with pytest.raises(GuardError):
        canonical_directory(str(Path(tmp_path.anchor)))


def test_symlink_is_not_followed(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.env").write_text("no-leer", encoding="utf-8")
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("el sistema no permitió crear el enlace")
    with pytest.raises(GuardError) as caught:
        resolve_inside(root, "escape/secret.env")
    assert caught.value.code == "SYMLINK_NOT_FOLLOWED"


def test_state_directory_cannot_live_inside_the_project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    state = root / "state"
    state.mkdir()
    with pytest.raises(GuardError) as caught:
        assert_separated(root, state)
    assert caught.value.code == "PROTECTS_CONTROL_DATA"
