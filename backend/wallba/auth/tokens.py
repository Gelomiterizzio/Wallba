"""Hashes opacos y comparación en tiempo constante.

El valor presentado es siempre el token en claro. El hash almacenado no se
acepta como si fuera el token.
"""

from __future__ import annotations

import hashlib
import hmac


def hash_opaque_token(raw: str) -> str:
    """Calcula el SHA-256 hexadecimal del token UTF-8."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def derive_csrf_token(session_token: str) -> str:
    """Token estable por sesión, separado del secreto de autenticación.

    El navegador presenta la cookie HttpOnly en cada petición. No se invierte
    ningún hash: el servidor deriva CSRF usando ese secreto como clave HMAC
    y una etiqueta fija de dominio. En almacenamiento solo queda su hash.
    """
    return hmac.new(
        session_token.encode("utf-8"), b"wallba-csrf-v1", hashlib.sha256
    ).hexdigest()


def token_matches(stored_hash: str, presented_raw: str | None) -> bool:
    """Compara el hash guardado con el hash del token presentado.

    Devuelve False si el token falta o está vacío. No trata el hash almacenado
    como un token válido.
    """
    if presented_raw is None or presented_raw == "":
        return False
    digest = hash_opaque_token(presented_raw)
    if len(stored_hash) != len(digest):
        return False
    return hmac.compare_digest(stored_hash, digest)
