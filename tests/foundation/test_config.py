"""Configuración fail-closed por rol (WAL-P1-002)."""

from __future__ import annotations

from pathlib import Path

import pytest

from wallba.foundation.config import ConfigError, load_settings

SECRET = "x" * 40


@pytest.fixture
def secret_file(tmp_path: Path) -> str:
    path = tmp_path / "secret"
    path.write_text(SECRET, encoding="utf-8")
    return str(path)


def control_env(tmp_path: Path, secret_file: str) -> dict[str, str]:
    return {
        "WALLBA_ROLE": "control",
        "WALLBA_DATA_DIR": str(tmp_path),
        "WALLBA_EXECUTOR_URL": "http://executor:8001",
        "WALLBA_CAPABILITY_KEY_ID": "key-1",
        "WALLBA_CAPABILITY_SECRET_FILE": secret_file,
        "WALLBA_EXECUTOR_TOKEN_FILE": secret_file,
    }


def test_valid_control_configuration_loads(tmp_path: Path, secret_file: str) -> None:
    settings = load_settings(control_env(tmp_path, secret_file))
    assert settings.role == "control"
    assert settings.environment_id == "protected-fixture"
    assert settings.control_db_path == tmp_path / "control.sqlite"


def test_secrets_are_not_in_repr(tmp_path: Path, secret_file: str) -> None:
    assert SECRET not in repr(load_settings(control_env(tmp_path, secret_file)))


@pytest.mark.parametrize("missing", ["WALLBA_CAPABILITY_SECRET_FILE", "WALLBA_EXECUTOR_TOKEN_FILE", "WALLBA_DATA_DIR"])
def test_missing_requirement_fails_closed(tmp_path: Path, secret_file: str, missing: str) -> None:
    env = control_env(tmp_path, secret_file)
    del env[missing]
    with pytest.raises(ConfigError):
        load_settings(env)


def test_unknown_role_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings({"WALLBA_ROLE": "root"})


def test_inline_secret_is_rejected(tmp_path: Path, secret_file: str) -> None:
    env = {**control_env(tmp_path, secret_file), "WALLBA_CAPABILITY_SECRET": SECRET}
    with pytest.raises(ConfigError):
        load_settings(env)


def test_short_secret_is_rejected(tmp_path: Path, secret_file: str) -> None:
    short = tmp_path / "short"
    short.write_text("corto", encoding="utf-8")
    env = {**control_env(tmp_path, secret_file), "WALLBA_CAPABILITY_SECRET_FILE": str(short)}
    with pytest.raises(ConfigError):
        load_settings(env)


def test_relative_data_dir_is_rejected(tmp_path: Path, secret_file: str) -> None:
    env = {**control_env(tmp_path, secret_file), "WALLBA_DATA_DIR": "datos"}
    with pytest.raises(ConfigError):
        load_settings(env)


def test_demo_profile_requires_baseline(tmp_path: Path, secret_file: str) -> None:
    env = {**control_env(tmp_path, secret_file), "WALLBA_DEMO_ENABLED": "true"}
    with pytest.raises(ConfigError):
        load_settings(env)


@pytest.mark.parametrize(
    "forbidden",
    [
        {"WALLBA_CAPABILITY_SECRET_FILE": "SECRET"},
        {"WALLBA_EXECUTOR_TOKEN_FILE": "SECRET"},
        {"WALLBA_EXECUTOR_URL": "http://executor:8001"},
        {"WALLBA_DATA_DIR": "DIR"},
    ],
)
def test_agent_cannot_receive_executor_authority(
    tmp_path: Path, secret_file: str, forbidden: dict[str, str]
) -> None:
    env = {
        "WALLBA_ROLE": "agent",
        "WALLBA_API_URL": "http://api:8000",
        "WALLBA_AGENT_BEARER_FILE": secret_file,
    }
    for key, value in forbidden.items():
        env[key] = {"SECRET": secret_file, "DIR": str(tmp_path)}.get(value, value)
    with pytest.raises(ConfigError):
        load_settings(env)


def test_baseline_cannot_receive_capability_secret(tmp_path: Path, secret_file: str) -> None:
    env = {
        "WALLBA_ROLE": "baseline",
        "WALLBA_DATA_DIR": str(tmp_path),
        "WALLBA_BASELINE_TOKEN_FILE": secret_file,
        "WALLBA_CAPABILITY_SECRET_FILE": secret_file,
    }
    with pytest.raises(ConfigError):
        load_settings(env)
