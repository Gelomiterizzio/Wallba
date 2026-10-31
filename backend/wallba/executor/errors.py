"""Errores del ejecutor. Sus códigos son seguros para exponer al gateway."""

from __future__ import annotations


class ToolError(Exception):
    """Fallo confirmado de una herramienta, sin efecto. Produce un receipt FAILED."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CapabilityRejected(Exception):
    """La solicitud no se despacha: cero efecto y sin reclamar nonce."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
