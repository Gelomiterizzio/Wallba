"""Sesiones humanas: login, CSRF estable por sesión y logout.

El hash SHA-256 no permite recuperar el token. El CSRF en claro solo sale
en la respuesta de login y de me; la cookie de sesión es otro secreto.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal, Protocol
from urllib.parse import urlsplit

from wallba.auth.clock import Clock
from wallba.auth.models import (
    AUTHENTICATION_REQUIRED,
    CSRF_REJECTED,
    ORIGIN_REJECTED,
    RATE_LIMITED,
    AuthError,
    HumanRecord,
    Role,
    SessionRecord,
    ensure_utc,
)
from wallba.auth.passwords import PasswordHasher
from wallba.auth.repository import AuthRepository, AuthStateConflict
from wallba.auth.tokens import derive_csrf_token, hash_opaque_token, token_matches

# Configuración y decisiones cerradas en docs/AUTH_IMPLEMENTATION.md.

ABSOLUTE_SESSION: timedelta = timedelta(hours=8)
IDLE: timedelta = timedelta(minutes=30)
COOKIE_MAX_AGE: int = 28800

_INVALID_CREDENTIALS: str = "Credenciales no válidas."
_SESSION_REQUIRED: str = "Autenticación requerida."
_ORIGIN_REJECTED: str = "Origen rechazado."
_CSRF_REJECTED: str = "CSRF rechazado."
_RATE_LIMITED: str = "Demasiados intentos."
_LOGGER = logging.getLogger("wallba.auth")


@dataclass(frozen=True, slots=True)
class AuthSettings:
    """Ajustes inyectados y validados; cookies inseguras solo en loopback."""

    allowed_origins: frozenset[str]
    cookie_name: str = "wallba_session"
    cookie_secure: bool = False
    cookie_path: str = "/"

    def __post_init__(self) -> None:
        if not self.cookie_name or any(c in self.cookie_name for c in " ;=\r\n"):
            raise ValueError("Nombre de cookie inválido.")
        if self.cookie_path != "/":
            raise ValueError("El path de sesión debe ser /.")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
                or "*" in origin
            ):
                raise ValueError("Se exige un Origin exacto sin path ni comodines.")
            if not self.cookie_secure and parsed.hostname not in {
                "localhost",
                "127.0.0.1",
                "::1",
            }:
                raise ValueError("Cookie sin Secure solo para loopback local.")


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """Login aceptado. El session_token no debe copiarse al JSON ni a los logs."""

    csrf_token: str
    roles: tuple[Role, ...]
    session_token: str
    principal_id: str
    username: str

    def __repr__(self) -> str:
        return (
            "IssuedSession(csrf_token='[redacted]', "
            f"roles={self.roles!r}, session_token='[redacted]', "
            f"principal_id={self.principal_id!r}, username={self.username!r})"
        )


@dataclass(frozen=True, slots=True)
class MeResult:
    """Identidad vigente y CSRF estable. La caducidad absoluta no se alarga."""

    principal_id: str
    username: str
    kind: Literal["human"]
    roles: tuple[Role, ...]
    csrf_token: str

    def __post_init__(self) -> None:
        if self.kind != "human":
            raise ValueError("me solo describe un principal humano.")

    def __repr__(self) -> str:
        return (
            "MeResult("
            f"principal_id={self.principal_id!r}, username={self.username!r}, "
            f"kind={self.kind!r}, roles={self.roles!r}, csrf_token='[redacted]')"
        )


class LoginRateLimiter(Protocol):
    """Límite de intentos cuyo sujeto aporta el llamador."""

    def is_limited(self, subject: str, now: datetime) -> bool:
        """Indica si el sujeto está bloqueado en este instante."""
        ...

    def record_failure(self, subject: str, now: datetime) -> None:
        """Registra un fallo de login."""
        ...

    def clear(self, subject: str) -> None:
        """Olvida los fallos tras una autenticación válida."""
        ...


def log_auth_event(event: str, request_id: str, code: str) -> None:
    """Registra solo el evento, el request_id y el código.

    No acepta username, contraseña, tokens, hashes ni CSRF.
    """
    _LOGGER.info("event=%s request_id=%s code=%s", event, request_id, code)


class AuthService:
    """Autenticación humana con sesión opaca, origen y CSRF sincronizado."""

    def __init__(
        self,
        repository: AuthRepository,
        clock: Clock,
        hasher: PasswordHasher,
        rate_limiter: LoginRateLimiter,
        settings: AuthSettings,
    ) -> None:
        self._repository: AuthRepository = repository
        self._clock: Clock = clock
        self._hasher: PasswordHasher = hasher
        self._rate_limiter: LoginRateLimiter = rate_limiter
        self.settings: AuthSettings = settings
        self._dummy_password_hash: str = hasher.hash_password(secrets.token_urlsafe(32))

    @property
    def repository(self) -> AuthRepository:
        return self._repository

    def authenticate_human(
        self, raw_session_token: str | None, request_id: str
    ) -> HumanRecord | AuthError:
        """Check live identity without depending on role claims supplied by a client."""
        result = self.me(raw_session_token, request_id)
        if isinstance(result, AuthError):
            return result
        human = self._repository.get_human_by_principal_id(result.principal_id)
        if human is None or human.disabled:
            return self._session_error(request_id)
        return human

    def login(
        self,
        username: str,
        password: str,
        origin: str | None,
        rate_subject: str,
        request_id: str,
    ) -> IssuedSession | AuthError:
        """Abre sesión si el origen, el cupo y la contraseña cuadran.

        Login no exige CSRF: todavía no hay sesión. Se protege con el origen
        exacto, el rate limit inyectado antes de verificar la contraseña y un
        401 uniforme. La cookie HttpOnly SameSite=Strict la emite el handler
        solo tras el éxito, y no forma parte de este resultado JSON.
        """
        now = self._now()
        # El adaptador durable reserva intentos atómicamente antes del hash
        # costoso. Los dobles anteriores conservan la interfaz de fallos.
        acquire = getattr(self._rate_limiter, "acquire", None)
        limited = (
            (not acquire(rate_subject, now))
            if acquire
            else self._rate_limiter.is_limited(rate_subject, now)
        )
        if limited:
            log_auth_event("login_rejected", request_id, RATE_LIMITED)
            return AuthError(
                status_code=429,
                code=RATE_LIMITED,
                message=_RATE_LIMITED,
                request_id=request_id,
            )
        if origin is None or origin not in self.settings.allowed_origins:
            self._rate_limiter.record_failure(rate_subject, now)
            log_auth_event("login_rejected", request_id, ORIGIN_REJECTED)
            return AuthError(
                status_code=403,
                code=ORIGIN_REJECTED,
                message=_ORIGIN_REJECTED,
                request_id=request_id,
            )
        human = self._repository.get_human_by_username(username)
        password_hash = (
            self._dummy_password_hash if human is None else human.password_hash
        )
        password_ok = self._hasher.verify_password(password, password_hash)
        if human is None or human.disabled or not password_ok:
            return self._reject_credentials(rate_subject, now, request_id)
        try:
            return self._issue_session(human, now, rate_subject, request_id)
        except AuthStateConflict:
            return self._reject_credentials(rate_subject, now, request_id)

    def me(
        self, raw_session_token: str | None, request_id: str
    ) -> MeResult | AuthError:
        """Devuelve CSRF derivado de la cookie de una sesión viva.

        No invierte hashes ni rota CSRF. Solo toca last_seen_at de forma
        condicionada a que la sesión y la identidad sigan activas. Nunca
        alarga las 8 h absolutas ni reactiva una sesión revocada.
        """
        found = self._live_session(raw_session_token, request_id, "me_rejected")
        if isinstance(found, AuthError):
            return found
        human = self._repository.get_human_by_principal_id(found.principal_id)
        if human is None or human.disabled:
            if human is not None and human.disabled:
                self._repository.revoke_session(found.token_hash, self._now())
            log_auth_event("me_rejected", request_id, AUTHENTICATION_REQUIRED)
            return self._session_error(request_id)
        assert raw_session_token is not None
        csrf_token = derive_csrf_token(raw_session_token)
        if not token_matches(found.csrf_hash, csrf_token):
            return self._session_error(request_id)
        updated = self._repository.update_session(
            replace(
                found,
                last_seen_at=self._now(),
            )
        )
        if updated is False:
            return self._session_error(request_id)
        log_auth_event("me_succeeded", request_id, "OK")
        return MeResult(
            principal_id=human.principal_id,
            username=human.username,
            kind="human",
            roles=_sorted_roles(human.roles),
            csrf_token=csrf_token,
        )

    def logout(
        self,
        raw_session_token: str | None,
        csrf_token: str | None,
        origin: str | None,
        request_id: str,
    ) -> None | AuthError:
        """Revoca la sesión viva si el origen y el CSRF vigente coinciden.

        No exige el rol approver. Una sesión inválida o caducada responde 401
        y, si estaba caducada, queda revocada. Un origen o un CSRF inválidos
        responden 403 y dejan la sesión vigente.
        """
        found = self._live_session(raw_session_token, request_id, "logout_rejected")
        if isinstance(found, AuthError):
            return found
        if origin is None or origin not in self.settings.allowed_origins:
            log_auth_event("logout_rejected", request_id, ORIGIN_REJECTED)
            return AuthError(
                status_code=403,
                code=ORIGIN_REJECTED,
                message=_ORIGIN_REJECTED,
                request_id=request_id,
            )
        if not token_matches(found.csrf_hash, csrf_token):
            log_auth_event("logout_rejected", request_id, CSRF_REJECTED)
            return AuthError(
                status_code=403,
                code=CSRF_REJECTED,
                message=_CSRF_REJECTED,
                request_id=request_id,
            )
        self._repository.revoke_session(found.token_hash, self._now())
        log_auth_event("logout_succeeded", request_id, "OK")
        return None

    def _issue_session(
        self,
        human: HumanRecord,
        now: datetime,
        rate_subject: str,
        request_id: str,
    ) -> IssuedSession:
        self._rate_limiter.clear(rate_subject)
        session_token = _new_opaque_token()
        csrf_token = derive_csrf_token(session_token)
        record = SessionRecord(
            token_hash=hash_opaque_token(session_token),
            principal_id=human.principal_id,
            csrf_hash=hash_opaque_token(csrf_token),
            expires_at=now + ABSOLUTE_SESSION,
            last_seen_at=now,
            revoked_at=None,
        )
        replace_sessions = getattr(self._repository, "replace_sessions", None)
        if replace_sessions:
            replace_sessions(record, now)
        else:
            self._repository.revoke_sessions_for_principal(human.principal_id, now)
            self._repository.insert_session(record)
        log_auth_event("login_succeeded", request_id, "OK")
        return IssuedSession(
            csrf_token=csrf_token,
            roles=_sorted_roles(human.roles),
            session_token=session_token,
            principal_id=human.principal_id,
            username=human.username,
        )

    def _reject_credentials(
        self, rate_subject: str, now: datetime, request_id: str
    ) -> AuthError:
        self._rate_limiter.record_failure(rate_subject, now)
        log_auth_event("login_rejected", request_id, AUTHENTICATION_REQUIRED)
        return AuthError(
            status_code=401,
            code=AUTHENTICATION_REQUIRED,
            message=_INVALID_CREDENTIALS,
            request_id=request_id,
        )

    def _live_session(
        self, raw_session_token: str | None, request_id: str, event: str
    ) -> SessionRecord | AuthError:
        if raw_session_token is None or raw_session_token == "":
            log_auth_event(event, request_id, AUTHENTICATION_REQUIRED)
            return self._session_error(request_id)
        record = self._repository.get_session(hash_opaque_token(raw_session_token))
        if record is None or record.revoked_at is not None:
            log_auth_event(event, request_id, AUTHENTICATION_REQUIRED)
            return self._session_error(request_id)
        now = self._now()
        if now >= record.expires_at or now >= record.last_seen_at + IDLE:
            self._repository.revoke_session(record.token_hash, now)
            log_auth_event(event, request_id, AUTHENTICATION_REQUIRED)
            return self._session_error(request_id)
        return record

    def _session_error(self, request_id: str) -> AuthError:
        return AuthError(
            status_code=401,
            code=AUTHENTICATION_REQUIRED,
            message=_SESSION_REQUIRED,
            request_id=request_id,
        )

    def _now(self) -> datetime:
        return ensure_utc(self._clock.now())


def _new_opaque_token() -> str:
    """Genera 256 bits en hexadecimal. No es un hash recuperable."""
    return secrets.token_hex(32)


def _sorted_roles(roles: frozenset[Role]) -> tuple[Role, ...]:
    return tuple(sorted(roles, key=lambda role: role.value))
