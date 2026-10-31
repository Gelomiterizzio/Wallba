"""Recorre el árbol con metadatos. No abre el contenido."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from wallba.guard.classifier import Classification, classify
from wallba.guard.errors import GuardError

SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".pytest_cache"}
MAX_FILES = 20_000
MAX_DEPTH = 30


@dataclass(frozen=True)
class Entry:
    relative_path: str
    parent_path: str
    name: str
    kind: str
    classification: Classification
    size_bytes: int | None
    mtime_ns: int | None


@dataclass(frozen=True)
class Scan:
    entries: tuple[Entry, ...]
    files: int
    directories: int
    truncated: bool
    listed_parents: frozenset[str]


def scan_tree(root: Path) -> Scan:
    entries: list[Entry] = []
    listed: set[str] = set()
    files = 0
    directories = 0
    truncated = False
    stack = [("", 0)]
    while stack:
        relative, depth = stack.pop()
        current = root if relative == "" else root.joinpath(*relative.split("/"))
        try:
            iterator = os.scandir(current)
        except OSError:
            if relative == "":
                raise GuardError("ROOT_UNREADABLE", "No se pudo leer la carpeta del proyecto.", 403)
            continue
        listed.add(relative)
        with iterator:
            children = sorted(iterator, key=lambda item: item.name)
        for child in children:
            name = child.name
            if name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
                continue
            child_relative = name if relative == "" else f"{relative}/{name}"
            try:
                if child.is_symlink():
                    entries.append(_entry(child, child_relative, relative, "symlink"))
                    continue
                if child.is_dir(follow_symlinks=False):
                    if name in SKIP:
                        continue
                    directories += 1
                    entries.append(_entry(child, child_relative, relative, "directory"))
                    if depth + 1 <= MAX_DEPTH:
                        stack.append((child_relative, depth + 1))
                    else:
                        truncated = True
                    continue
                if child.is_file(follow_symlinks=False):
                    files += 1
                    if files > MAX_FILES:
                        truncated = True
                        return Scan(tuple(entries), files, directories, True, frozenset(listed))
                    entries.append(_entry(child, child_relative, relative, "file"))
            except OSError:
                continue
    return Scan(tuple(entries), files, directories, truncated, frozenset(listed))


def _entry(child: os.DirEntry[str], relative: str, parent: str, kind: str) -> Entry:
    size = mtime = None
    try:
        stat = child.stat(follow_symlinks=False)
        size, mtime = stat.st_size, stat.st_mtime_ns
    except OSError:
        pass
    return Entry(relative, parent, child.name, kind, classify(relative, kind), size, mtime)
