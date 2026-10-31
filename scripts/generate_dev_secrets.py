"""Genera secretos locales aleatorios en secrets/. Nunca sobrescribe ni los imprime.

Uso (desde la raíz): python scripts/generate_dev_secrets.py
"""

from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("capability_secret", "executor_token", "baseline_token", "agent_bearer")


def generate(directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    created = []
    for name in NAMES:
        path = directory / name
        if path.exists():
            continue
        path.write_text(secrets.token_hex(32), encoding="ascii")
        path.chmod(0o600)
        created.append(name)
    return created


if __name__ == "__main__":
    for item in generate(ROOT / "secrets"):
        print(f"creado: secrets/{item}")
