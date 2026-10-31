"""Configuración tipada por rol de proceso. Falla cerrado al iniciar.

Los secretos solo se leen desde archivos montados (`*_FILE`); un valor en el
entorno, un secreto ajeno al rol o una ruta relativa impiden arrancar.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args

ProcessRole = Literal["control", "executor", "baseline", "agent"]

MIN_SECRET_BYTES = 32
SECRET_VARS = {
    "capability_secret": "WALLBA_CAPABILITY_SECRET_FILE",
    "executor_token": "WALLBA_EXECUTOR_TOKEN_FILE",
    "baseline_token": "WALLBA_BASELINE_TOKEN_FILE",
    "agent_bearer": "WALLBA_AGENT_BEARER_FILE",
}
REQUIRED_SECRETS: dict[str, set[str]] = {
    "control": {"capability_secret", "executor_token"},
    "executor": {"capability_secret", "executor_token"},
    "baseline": {"baseline_token"},
    "agent": {"agent_bearer"},
}
# El control solo necesita el token baseline con el perfil demo.
OPTIONAL_SECRETS: dict[str, set[str]] = {"control": {"baseline_token"}}
REQUIRED_VALUES: dict[str, set[str]] = {
    "control": {"WALLBA_DATA_DIR", "WALLBA_EXECUTOR_URL", "WALLBA_CAPABILITY_KEY_ID"},
    "executor": {"WALLBA_DATA_DIR", "WALLBA_CAPABILITY_KEY_ID"},
    "baseline": {"WALLBA_DATA_DIR"},
    "agent": {"WALLBA_API_URL"},
}
FORBIDDEN_VALUES: dict[str, set[str]] = {
    "control": set(),
    "executor": {"WALLBA_API_URL", "WALLBA_EXECUTOR_URL", "WALLBA_BASELINE_URL"},
    "baseline": {"WALLBA_API_URL", "WALLBA_EXECUTOR_URL", "WALLBA_CAPABILITY_KEY_ID"},
    "agent": {
        "WALLBA_DATA_DIR",
        "WALLBA_EXECUTOR_URL",
        "WALLBA_BASELINE_URL",
        "WALLBA_CAPABILITY_KEY_ID",
    },
}
DEFAULT_ENVIRONMENT = {
    "control": "protected-fixture",
    "executor": "protected-fixture",
    "baseline": "baseline-fixture",
    "agent": "protected-fixture",
}


class ConfigError(ValueError):
    """Configuración inválida: el proceso no debe arrancar."""


@dataclass(frozen=True)
class Settings:
    role: ProcessRole
    environment_id: str
    demo_enabled: bool = False
    data_dir: Path | None = None
    allowed_origin: str = "http://127.0.0.1:8080"
    capability_key_id: str | None = None
    executor_url: str | None = None
    baseline_url: str | None = None
    api_url: str | None = None
    # repr=False: los secretos no aparecen en logs ni en errores.
    capability_secret: bytes | None = field(default=None, repr=False)
    executor_token: str | None = field(default=None, repr=False)
    baseline_token: str | None = field(default=None, repr=False)
    agent_bearer: str | None = field(default=None, repr=False)

    @property
    def control_db_path(self) -> Path:
        return self._data_path("control.sqlite")

    @property
    def sandbox_root(self) -> Path:
        return self._data_path("sandboxes")

    def _data_path(self, name: str) -> Path:
        if self.data_dir is None:
            raise ConfigError(f"el rol {self.role} no tiene directorio de datos")
        return self.data_dir / name


def _read_secret(var: str, env: Mapping[str, str]) -> bytes:
    path = Path(env[var])
    if not path.is_absolute():
        raise ConfigError(f"{var} debe ser una ruta absoluta")
    try:
        secret = path.read_bytes().strip()
    except OSError as exc:
        raise ConfigError(f"no se pudo leer el secreto de {var}") from exc
    if len(secret) < MIN_SECRET_BYTES:
        raise ConfigError(f"{var} debe tener al menos {MIN_SECRET_BYTES} bytes")
    return secret


def _load_secrets(role: str, env: Mapping[str, str]) -> dict[str, bytes]:
    required = REQUIRED_SECRETS[role]
    optional = OPTIONAL_SECRETS.get(role, set())
    secrets: dict[str, bytes] = {}
    for name, var in SECRET_VARS.items():
        if var.removesuffix("_FILE") in env:
            raise ConfigError(f"{var.removesuffix('_FILE')}: los secretos solo se admiten por archivo")
        present = bool(env.get(var))
        if name in required and not present:
            raise ConfigError(f"falta el secreto requerido {var}")
        if present and name not in required | optional:
            raise ConfigError(f"el rol {role} no puede recibir {var}")
        if present:
            secrets[name] = _read_secret(var, env)
    return secrets


def _parse_bool(var: str, env: Mapping[str, str]) -> bool:
    raw = env.get(var, "false")
    if raw not in {"true", "false"}:
        raise ConfigError(f"{var} debe ser 'true' o 'false'")
    return raw == "true"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    role = env.get("WALLBA_ROLE")
    if role not in get_args(ProcessRole):
        raise ConfigError("WALLBA_ROLE debe ser control, executor, baseline o agent")
    for var in REQUIRED_VALUES[role]:
        if not env.get(var):
            raise ConfigError(f"falta la configuración requerida {var}")
    for var in FORBIDDEN_VALUES[role]:
        if env.get(var):
            raise ConfigError(f"el rol {role} no puede recibir {var}")

    data_dir = Path(env["WALLBA_DATA_DIR"]) if env.get("WALLBA_DATA_DIR") else None
    if data_dir is not None and not data_dir.is_absolute():
        raise ConfigError("WALLBA_DATA_DIR debe ser una ruta absoluta")

    secrets = _load_secrets(role, env)
    demo_enabled = _parse_bool("WALLBA_DEMO_ENABLED", env)
    if role == "control" and demo_enabled:
        if not env.get("WALLBA_BASELINE_URL") or "baseline_token" not in secrets:
            raise ConfigError("el perfil demo requiere WALLBA_BASELINE_URL y su token")

    def text(name: str) -> str | None:
        value = secrets.get(name)
        return value.decode("utf-8") if value is not None else None

    return Settings(
        role=role,
        environment_id=env.get("WALLBA_ENVIRONMENT_ID", DEFAULT_ENVIRONMENT[role]),
        demo_enabled=demo_enabled,
        data_dir=data_dir,
        allowed_origin=env.get("WALLBA_ALLOWED_ORIGIN", "http://127.0.0.1:8080"),
        capability_key_id=env.get("WALLBA_CAPABILITY_KEY_ID"),
        executor_url=env.get("WALLBA_EXECUTOR_URL"),
        baseline_url=env.get("WALLBA_BASELINE_URL"),
        api_url=env.get("WALLBA_API_URL"),
        capability_secret=secrets.get("capability_secret"),
        executor_token=text("executor_token"),
        baseline_token=text("baseline_token"),
        agent_bearer=text("agent_bearer"),
    )
