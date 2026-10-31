"""Base strict model y validadores compartidos por todos los DTO de WALLBA."""

from __future__ import annotations

import unicodedata

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Modelo estricto: sin coerción de tipos y sin campos extra."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def ensure_nfc(value: str, field: str) -> str:
    """Rechaza texto que no esté en Unicode NFC."""
    if not unicodedata.is_normalized("NFC", value):
        raise ValueError(f"{field} debe estar en Unicode NFC")
    return value
