"""Reloj inyectable. La hora de autorización siempre es UTC consciente."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Fuente de hora sustituible en pruebas."""

    def now(self) -> datetime:
        """Devuelve el instante actual, consciente y en UTC."""
        ...


class SystemClock:
    """Reloj del sistema anclado a UTC."""

    def now(self) -> datetime:
        """Devuelve la hora actual del sistema en UTC consciente."""
        return datetime.now(UTC)
