"""Decisión previa a la operación. Observar no es bloquear."""

from __future__ import annotations

from dataclasses import dataclass

KNOWN = frozenset({"monitor", "alert", "block_read", "block_write", "block_all"})
WRITE = frozenset({"write", "delete", "rename"})


@dataclass(frozen=True)
class Decision:
    effect: str
    preventive: bool
    covered: bool
    posture: str | None
    reason: str


def decide(posture: str | None, operation: str) -> Decision:
    if posture is None:
        return Decision(
            "ALLOW",
            False,
            False,
            None,
            "La ruta no tiene política. La operación no queda bloqueada.",
        )
    if posture not in KNOWN:
        return Decision(
            "DENY",
            True,
            True,
            posture,
            "La política no se reconoce. Se deniega antes de ejecutar.",
        )
    if posture in {"monitor", "alert"}:
        return Decision(
            "ALLOW",
            False,
            True,
            posture,
            "La política registra la operación y no la impide.",
        )
    if posture == "block_read" and operation == "read":
        return Decision("DENY", True, True, posture, "Lectura denegada antes de abrir el archivo.")
    if posture == "block_write" and operation in WRITE:
        return Decision("DENY", True, True, posture, "Escritura denegada antes de modificar el archivo.")
    if posture == "block_all" and (operation == "read" or operation in WRITE):
        return Decision("DENY", True, True, posture, "Operación denegada antes de ejecutarse.")
    return Decision(
        "ALLOW",
        False,
        True,
        posture,
        "Esta política no cubre la operación de forma preventiva.",
    )
