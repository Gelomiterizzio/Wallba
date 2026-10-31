"""Publicación y activación. Guardar una versión no mueve el puntero activo."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Protocol

from wallba.policy.loader import load_policy
from wallba.policy.models import TOKEN, PolicyFieldError, PolicySnapshot
from wallba.policy.repository import (
    ActivationConflict,
    AuditFailure,
    AuditSink,
    InvalidCursor,
    PolicyStorageError,
    SqlitePolicyRepository,
    VersionConflict,
    VersionNotFound,
    VersionPage,
    VersionRecord,
    VersionSummary,
)
from wallba.policy.schemas import ValidationReport

_TOKEN = re.compile(TOKEN)


class Clock(Protocol):
    def now(self) -> datetime:
        """Reloj inyectado. El evaluador no consulta la hora."""


class InvalidPolicy(Exception):
    def __init__(self, errors: tuple[PolicyFieldError, ...]) -> None:
        self.errors = errors
        super().__init__("POLICY_INVALID")


class PolicyConflict(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class PolicyNotFound(Exception):
    pass


class PolicyUnavailable(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class PolicyService:
    def __init__(self, repository: SqlitePolicyRepository, clock: Clock, audit: AuditSink) -> None:
        self._repository = repository
        self._clock = clock
        self._audit = audit

    def validate_content(self, content: str | bytes, format: str) -> ValidationReport:
        return load_policy(content, format)

    def create_version(self, policy_id: str, content: bytes, created_by: str) -> VersionSummary:
        _require_token(policy_id, "policy_id")
        _require_token(created_by, "created_by")
        report = load_policy(content, "json")
        if not report.valid or report.document is None:
            raise InvalidPolicy(report.errors)
        if report.document.policy_id != policy_id:
            raise InvalidPolicy((PolicyFieldError(field="policy_id", code="invalid_value"),))
        try:
            return self._repository.save_version(report.document, created_by, _format_utc(self._clock.now()))
        except VersionConflict as exc:
            raise PolicyConflict("CONFLICT") from exc
        except PolicyStorageError as exc:
            raise PolicyUnavailable("AUTHORIZATION_UNAVAILABLE") from exc

    def activate(
        self,
        policy_id: str,
        version: int,
        expected_active_version: int | None,
        actor_id: str,
        expected_active_policy_id: str | None = None,
    ) -> PolicySnapshot:
        _require_token(policy_id, "policy_id")
        _require_token(actor_id, "actor_id")
        if expected_active_policy_id is not None:
            _require_token(expected_active_policy_id, "expected_active_policy_id")
        try:
            return self._repository.activate(
                policy_id=policy_id,
                version=version,
                expected_active_version=expected_active_version,
                actor_id=actor_id,
                occurred_at=_format_utc(self._clock.now()),
                audit=self._audit,
                expected_active_policy_id=expected_active_policy_id,
            )
        except ActivationConflict as exc:
            raise PolicyConflict("STALE_POLICY") from exc
        except VersionNotFound as exc:
            raise PolicyNotFound() from exc
        except AuditFailure as exc:
            raise PolicyUnavailable("AUDIT_UNAVAILABLE") from exc
        except PolicyStorageError as exc:
            raise PolicyUnavailable("AUTHORIZATION_UNAVAILABLE") from exc

    def get_version(self, policy_id: str, version: int) -> VersionRecord:
        _require_token(policy_id, "policy_id")
        try:
            found = self._repository.get_version(policy_id, version)
        except PolicyStorageError as exc:
            raise PolicyUnavailable("AUTHORIZATION_UNAVAILABLE") from exc
        if found is None:
            raise PolicyNotFound()
        return found

    def list_versions(self, cursor: str | None, limit: int) -> VersionPage:
        try:
            return self._repository.list_versions(cursor, limit)
        except InvalidCursor as exc:
            raise InvalidCursor() from exc
        except PolicyStorageError as exc:
            raise PolicyUnavailable("AUTHORIZATION_UNAVAILABLE") from exc

    def get_active_snapshot(self) -> PolicySnapshot | None:
        try:
            return self._repository.get_active_snapshot()
        except PolicyStorageError as exc:
            raise PolicyUnavailable("AUTHORIZATION_UNAVAILABLE") from exc


def _require_token(value: str, field: str) -> None:
    if not isinstance(value, str) or _TOKEN.fullmatch(value) is None:
        raise InvalidPolicy((PolicyFieldError(field=field, code="invalid_value"),))


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PolicyUnavailable("AUTHORIZATION_UNAVAILABLE")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
