"""Recorrido del proyecto. No abre el contenido de los archivos."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from wallba.protection.classifier import Classification, classify_path, extension_label
from wallba.protection.errors import ProtectionError
from wallba.protection.paths import is_inside

SKIP_DIRECTORIES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
}
MAX_ENTRIES = 20_000
MAX_DEPTH = 30


@dataclass(frozen=True)
class Observed:
    relative_path: str
    parent_path: str
    name: str
    kind: str
    classification: Classification
    size_bytes: int | None
    mtime_ns: int | None
    extension: str


@dataclass(frozen=True)
class ScanResult:
    entries: tuple[Observed, ...]
    files: int
    directories: int
    truncated: bool
    listed_parents: frozenset[str]


def _stamp(entry: os.DirEntry[str]) -> tuple[int | None, int | None]:
    try:
        stat = entry.stat(follow_symlinks=False)
    except OSError:
        return None, None
    return stat.st_size, stat.st_mtime_ns


def _symlink_escapes(root: Path, entry: os.DirEntry[str]) -> bool:
    try:
        target = Path(entry.path).resolve(strict=False)
    except OSError:
        return True
    root_resolved = root.resolve()
    return not target.is_relative_to(root_resolved)


def scan_tree(root: Path) -> ScanResult:
    entries: list[Observed] = []
    listed: set[str] = set()
    files = 0
    directories = 0
    truncated = False
    stack: list[tuple[str, int]] = [("", 0)]

    while stack:
        relative, depth = stack.pop()
        current = root if relative == "" else root.joinpath(*relative.split("/"))
        try:
            iterator = os.scandir(current)
        except OSError:
            if relative == "":
                raise ProtectionError("ROOT_UNREADABLE", "No se pudo leer la carpeta del proyecto.", 403)
            entries.append(
                Observed(
                    relative,
                    relative.rsplit("/", 1)[0] if "/" in relative else "",
                    relative.rsplit("/", 1)[-1],
                    "directory",
                    Classification(
                        "MEDIUM",
                        "access_config",
                        ("No se pudo leer esta carpeta. La cobertura de esta rama está incompleta.",),
                    ),
                    None,
                    None,
                    "",
                )
            )
            continue
        listed.add(relative)
        children = []
        with iterator:
            for child in iterator:
                children.append(child)
        children.sort(key=lambda item: item.name)
        for child in children:
            name = child.name
            if name in {".", ".."} or "\x00" in name or "/" in name or "\\" in name:
                continue
            child_relative = name if relative == "" else f"{relative}/{name}"
            try:
                link = child.is_symlink()
            except OSError:
                continue
            if link:
                size, mtime = _stamp(child)
                entries.append(
                    Observed(
                        child_relative,
                        relative,
                        name,
                        "symlink",
                        classify_path(child_relative, "symlink", symlink_escapes=_symlink_escapes(root, child)),
                        size,
                        mtime,
                        extension_label(name),
                    )
                )
                continue
            try:
                is_dir = child.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                if name in SKIP_DIRECTORIES:
                    continue
                directories += 1
                size, mtime = _stamp(child)
                entries.append(
                    Observed(
                        child_relative,
                        relative,
                        name,
                        "directory",
                        classify_path(child_relative, "directory"),
                        size,
                        mtime,
                        "",
                    )
                )
                if depth + 1 <= MAX_DEPTH:
                    stack.append((child_relative, depth + 1))
                else:
                    truncated = True
                continue
            try:
                is_file = child.is_file(follow_symlinks=False)
            except OSError:
                continue
            if not is_file:
                continue
            files += 1
            if files > MAX_ENTRIES:
                truncated = True
                break
            size, mtime = _stamp(child)
            entries.append(
                Observed(
                    child_relative,
                    relative,
                    name,
                    "file",
                    classify_path(child_relative, "file"),
                    size,
                    mtime,
                    extension_label(name),
                )
            )
        if truncated and files > MAX_ENTRIES:
            break

    # Un enlace que escapa del proyecto no debe aparecer como hijo navegable.
    confined = []
    for item in entries:
        if item.kind == "symlink":
            try:
                target = (root / item.relative_path).resolve(strict=False)
                if is_inside(target, root.resolve()) or target == root.resolve():
                    confined.append(item)
                else:
                    confined.append(item)
            except OSError:
                confined.append(item)
            continue
        confined.append(item)
    return ScanResult(tuple(confined), files, directories, truncated, frozenset(listed))
