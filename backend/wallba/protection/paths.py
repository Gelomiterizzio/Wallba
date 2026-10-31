"""Confinamiento de rutas. No se siguen enlaces y no se sale del proyecto."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from wallba.protection.errors import ProtectionError


def canonical_directory(raw: str) -> Path:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise ProtectionError("PATH_INVALID", "La ruta del proyecto no es válida.")
    path = Path(raw)
    if not path.is_absolute():
        raise ProtectionError("PATH_NOT_ABSOLUTE", "Indica una ruta absoluta de la carpeta del proyecto.")
    try:
        if not path.exists():
            raise ProtectionError("ROOT_NOT_FOUND", "La carpeta no existe.", 404)
        if path.is_symlink():
            resolved = path.resolve(strict=True)
        else:
            resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ProtectionError("ROOT_UNREADABLE", "No se pudo leer la carpeta del proyecto.", 403) from exc
    if not resolved.is_dir():
        raise ProtectionError("ROOT_NOT_DIRECTORY", "La ruta no es una carpeta.")
    if resolved.parent == resolved:
        raise ProtectionError(
            "ROOT_TOO_BROAD",
            "Elige la carpeta de un proyecto. No se analiza la raíz del disco.",
        )
    return resolved


def relative_parts(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or value == "" or "\x00" in value:
        raise ProtectionError("PATH_INVALID", "La ruta interna no es válida.")
    if len(value) > 512:
        raise ProtectionError("PATH_INVALID", "La ruta interna supera el límite.")
    normalized = unicodedata.normalize("NFC", value.replace("\\", "/"))
    if normalized.startswith("/"):
        raise ProtectionError("PATH_INVALID", "La ruta debe ser interna al proyecto.")
    parts = tuple(normalized.split("/"))
    if any(part in {"", ".", ".."} or part.endswith(":") or len(part) > 255 for part in parts):
        raise ProtectionError("PATH_INVALID", "La ruta contiene segmentos no permitidos.")
    return parts


def is_inside(child: Path, parent: Path) -> bool:
    return child != parent and child.is_relative_to(parent)


def assert_separated(root: Path, state_dir: Path) -> None:
    """El estado de protección no puede vivir dentro del proyecto analizado."""
    root = root.resolve()
    state = state_dir.resolve()
    if root == state or is_inside(state, root) or is_inside(root, state):
        raise ProtectionError(
            "PROTECTS_CONTROL_DATA",
            "Esa carpeta se solapa con el estado interno de WALLBA. Elige otro proyecto.",
        )


def resolve_inside(root: Path, relative: str) -> Path:
    """Devuelve la ruta real sin atravesar enlaces simbólicos."""
    current = root
    parts = relative_parts(relative)
    for index, part in enumerate(parts):
        current = current / part
        try:
            if current.is_symlink():
                raise ProtectionError(
                    "SYMLINK_NOT_FOLLOWED",
                    "No se atraviesan enlaces simbólicos.",
                )
            if not current.exists():
                raise ProtectionError("PATH_NOT_FOUND", "La ruta no existe dentro del proyecto.", 404)
        except OSError as exc:
            raise ProtectionError("PATH_UNREADABLE", "No se pudo comprobar la ruta.", 403) from exc
        if index < len(parts) - 1 and not current.is_dir():
            raise ProtectionError("NOT_A_DIRECTORY", "Un tramo de la ruta no es una carpeta.")
    try:
        resolved = current.resolve()
        base = root.resolve()
    except OSError as exc:
        raise ProtectionError("PATH_UNREADABLE", "No se pudo comprobar la ruta.", 403) from exc
    if not resolved.is_relative_to(base):
        raise ProtectionError("PATH_ESCAPE", "La ruta queda fuera del proyecto.")
    return current


def to_relative(root: Path, target: Path) -> str:
    return target.resolve().relative_to(root.resolve()).as_posix()
