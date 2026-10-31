"""Confinamiento. No se siguen enlaces ni se sale de la carpeta del proyecto."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from wallba.guard.errors import GuardError


def canonical_directory(raw: str) -> Path:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise GuardError("PATH_INVALID", "La ruta del proyecto no es válida.")
    path = Path(raw)
    if not path.is_absolute():
        raise GuardError("PATH_NOT_ABSOLUTE", "Indica la ruta absoluta de la carpeta del proyecto.")
    try:
        if not path.exists():
            raise GuardError("ROOT_NOT_FOUND", "La carpeta no existe.", 404)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise GuardError("ROOT_UNREADABLE", "No se pudo leer la carpeta del proyecto.", 403) from exc
    if not resolved.is_dir() or resolved.parent == resolved:
        raise GuardError("ROOT_NOT_ALLOWED", "Elige una carpeta de proyecto, no un archivo ni la raíz del disco.")
    return resolved


def relative_parts(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or value == "" or "\x00" in value or len(value) > 512:
        raise GuardError("PATH_INVALID", "La ruta interna no es válida.")
    normalized = unicodedata.normalize("NFC", value.replace("\\", "/"))
    if normalized.startswith("/"):
        raise GuardError("PATH_INVALID", "La ruta debe ser interna al proyecto.")
    parts = tuple(normalized.split("/"))
    if any(part in {"", ".", ".."} or len(part) > 255 for part in parts):
        raise GuardError("PATH_INVALID", "La ruta contiene segmentos no permitidos.")
    return parts


def assert_separated(root: Path, state_dir: Path) -> None:
    root = root.resolve()
    state = state_dir.resolve()
    if root == state or state.is_relative_to(root) or root.is_relative_to(state):
        raise GuardError(
            "PROTECTS_CONTROL_DATA",
            "Esa carpeta se solapa con el estado de WALLBA. Elige otro proyecto.",
        )


def resolve_inside(root: Path, relative: str) -> Path:
    current = root
    for index, part in enumerate(relative_parts(relative)):
        current = current / part
        try:
            if current.is_symlink():
                raise GuardError("SYMLINK_NOT_FOLLOWED", "No se atraviesan enlaces simbólicos.")
            if not current.exists():
                raise GuardError("PATH_NOT_FOUND", "La ruta no existe dentro del proyecto.", 404)
        except OSError as exc:
            raise GuardError("PATH_UNREADABLE", "No se pudo comprobar la ruta.", 403) from exc
        if index < len(relative_parts(relative)) - 1 and not current.is_dir():
            raise GuardError("NOT_A_DIRECTORY", "Un tramo de la ruta no es una carpeta.")
    try:
        if not current.resolve().is_relative_to(root.resolve()):
            raise GuardError("PATH_ESCAPE", "La ruta queda fuera del proyecto.")
    except OSError as exc:
        raise GuardError("PATH_UNREADABLE", "No se pudo comprobar la ruta.", 403) from exc
    return current
