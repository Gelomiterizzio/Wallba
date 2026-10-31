"""Base strict model y tipos acotados compartidos por todos los DTO de WALLBA."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, StringConstraints

UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
ALLOWED_CONTROL_CHARS = {"\n", "\t"}


class StrictModel(BaseModel):
    """Modelo estricto: sin coerción de tipos y sin campos extra."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def ensure_nfc(value: str, field: str = "texto") -> str:
    """Rechaza texto que no esté en Unicode NFC."""
    if not unicodedata.is_normalized("NFC", value):
        raise ValueError(f"{field} debe estar en Unicode NFC")
    return value


def ensure_safe_text(value: str) -> str:
    """Exige NFC y rechaza bytes nulos y caracteres de control."""
    ensure_nfc(value)
    for char in value:
        if unicodedata.category(char) == "Cc" and char not in ALLOWED_CONTROL_CHARS:
            raise ValueError("el texto contiene caracteres de control")
    return value


def ensure_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("el timestamp debe estar en UTC")
    return value


Uuid = Annotated[str, StringConstraints(pattern=UUID_PATTERN)]
Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SafeText = Annotated[str, AfterValidator(ensure_safe_text)]
UtcDatetime = Annotated[AwareDatetime, AfterValidator(ensure_utc)]
