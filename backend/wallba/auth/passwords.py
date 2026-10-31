"""Puerto de contraseñas. Argon2id no se implementa a mano ni se importa al cargar."""

from __future__ import annotations

from typing import Protocol


class AuthDependencyError(RuntimeError):
    """Dependencia ausente. No acredita el algoritmo ni el framework."""


class PasswordHasher(Protocol):
    """Hash y verificación de contraseñas humanas."""

    def hash_password(self, password: str) -> str:
        """Devuelve un hash no reversible de la contraseña."""
        ...

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Compara la contraseña con el hash almacenado."""
        ...


class Argon2PasswordHasher:
    """Adaptador de argon2-cffi, verificado en tests/auth/test_integration.py.

    El import ocurre solo al construir la clase. Si la librería no está,
    se señala el hueco y no se inventa un Argon2 propio.
    """

    def __init__(self) -> None:
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import (
                InvalidHashError,
                VerificationError,
                VerifyMismatchError,
            )
        except ImportError as exc:
            raise AuthDependencyError(
                "Falta argon2-cffi; Argon2id no está verificado."
            ) from exc
        self._hasher = PasswordHasher()
        self._verify_errors = (VerifyMismatchError, VerificationError, InvalidHashError)

    def hash_password(self, password: str) -> str:
        """Delega el hash Argon2id en argon2-cffi."""
        return str(self._hasher.hash(password))

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Delega la verificación en argon2-cffi."""
        try:
            return bool(self._hasher.verify(password_hash, password))
        except self._verify_errors:
            return False
