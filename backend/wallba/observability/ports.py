"""Puerto que consumen los productores de eventos y sus errores."""

from __future__ import annotations

from wallba.contracts.ports import AuditEventDraft, AuditSink

__all__ = ["AuditEventDraft", "AuditSink", "AuditSchemaError", "AuditWriteError"]


class AuditSchemaError(ValueError):
    """Un campo tipado no cumple el esquema. El evento no se escribe."""


class AuditWriteError(RuntimeError):
    """No se pudo persistir. Antes de un efecto, el productor no debe ejecutar."""
