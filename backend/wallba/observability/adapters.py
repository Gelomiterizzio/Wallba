"""Adaptadores del AuditWriter hacia productores con su propio contrato de error."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from wallba.observability.writer import AuditWriter
from wallba.policy.repository import AuditFailure


class PolicyAuditSink:
    """Traduce cualquier fallo a AuditFailure: P2 revierte la activación y responde 503."""

    def __init__(self, writer: AuditWriter) -> None:
        self._writer = writer

    def append(self, event: Mapping[str, object], connection: Any) -> None:
        try:
            self._writer.append(event, connection)
        except Exception as exc:  # noqa: BLE001 - sin auditoría la activación no ocurre
            raise AuditFailure() from exc
