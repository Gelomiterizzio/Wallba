"""Tipos comunes de los adaptadores de herramientas."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection

from wallba.contracts.results import ToolResult


@dataclass(frozen=True)
class ToolContext:
    connection: Connection
    execution_id: str
    tenant_marker: str
    files_dir: Path


@dataclass(frozen=True)
class ToolOutcome:
    result: ToolResult
    effect_count: int
