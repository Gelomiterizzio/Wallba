"""Entornos sintéticos desechables, uno por run_id, con marcador de pertenencia."""

from __future__ import annotations

import json
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, text

from wallba.contracts.api import ResourceSnapshot
from wallba.contracts.canonical import canonical_json, sha256_hex
from wallba.contracts.common import UUID_PATTERN
from wallba.demo.fixtures import INITIAL_RESOURCE_VERSIONS, Fixture, build_fixture, fixture_digest
from wallba.foundation.database import create_sqlite_engine, write_transaction

MARKER_NAME = ".wallba-sandbox.json"
MARKER_LABEL = "wallba-sandbox"
DB_NAME = "executor.sqlite"

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS execution_journal (
        execution_id TEXT PRIMARY KEY,
        nonce_hash TEXT NOT NULL UNIQUE,
        request_id TEXT NOT NULL,
        request_digest TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('SUCCEEDED','FAILED','UNKNOWN')),
        result_digest TEXT,
        result_json TEXT,
        effect_count INTEGER,
        evidence_id TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS demo_records (
        id TEXT PRIMARY KEY,
        tenant_marker TEXT NOT NULL,
        label TEXT NOT NULL,
        version INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS outbox (
        message_id TEXT PRIMARY KEY,
        execution_id TEXT NOT NULL UNIQUE,
        to_address TEXT NOT NULL,
        subject TEXT NOT NULL,
        body_digest TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status = 'SIMULATED')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resource_versions (
        resource_id TEXT PRIMARY KEY,
        version INTEGER NOT NULL
    )
    """,
)


class SandboxError(ValueError):
    """Operación fuera de los límites del sandbox."""


@dataclass
class Sandbox:
    run_id: str
    path: Path
    engine: Engine
    fixture_digest: str

    @property
    def files_dir(self) -> Path:
        return self.path / "files"

    def snapshot(self) -> ResourceSnapshot:
        with self.engine.connect() as connection:
            records = connection.execute(
                text("SELECT id, label, version FROM demo_records ORDER BY id")
            ).all()
            outbox = connection.execute(
                text("SELECT to_address, subject, body_digest FROM outbox ORDER BY to_address, body_digest")
            ).all()
            journal_count = connection.execute(text("SELECT COUNT(*) FROM execution_journal")).scalar_one()
        # El estado funcional excluye IDs de entorno y journal: es comparable entre lados.
        state = {
            "records": [[r.id, r.label, r.version] for r in records],
            "outbox": [[m.to_address, m.subject, m.body_digest] for m in outbox],
            "files": [
                [item.name, sha256_hex(item.read_bytes())] for item in sorted(self.files_dir.iterdir())
            ],
        }
        return ResourceSnapshot(
            state_digest=sha256_hex(canonical_json(state)),
            record_count=len(records),
            outbox_count=len(outbox),
            journal_count=journal_count,
        )


class SandboxManager:
    def __init__(self, root: Path, side: str) -> None:
        self._root = root.resolve()
        self._side = side
        self._open: dict[str, Sandbox] = {}

    def prepare(self, run_id: str, seed: int) -> Sandbox:
        path = self._path_for(run_id)
        if path.exists():
            raise SandboxError("ya existe un sandbox para ese run_id")
        fixture = build_fixture(seed)
        (path / "files").mkdir(parents=True)
        self._write_marker(path, run_id, fixture)
        self._write_files(path, fixture)
        sandbox = self._open_sandbox(run_id, path, fixture_digest(fixture))
        self._seed_database(sandbox, fixture)
        return sandbox

    def get(self, run_id: str) -> Sandbox:
        if run_id in self._open:
            return self._open[run_id]
        path = self._path_for(run_id)
        marker = self._read_marker(path, run_id)
        return self._open_sandbox(run_id, path, marker["fixture_digest"])

    def run_ids(self) -> list[str]:
        if not self._root.exists():
            return []
        return [item.name for item in self._root.iterdir() if (item / MARKER_NAME).is_file()]

    def reset(self, run_id: str) -> None:
        """Borra solo un directorio propio y etiquetado con ese run_id."""
        path = self._path_for(run_id)
        self._read_marker(path, run_id)
        sandbox = self._open.pop(run_id, None)
        if sandbox is not None:
            sandbox.engine.dispose()
        shutil.rmtree(path, onexc=_force_remove)

    def dispose(self) -> None:
        for sandbox in self._open.values():
            sandbox.engine.dispose()
        self._open.clear()

    def _path_for(self, run_id: str) -> Path:
        if not re.fullmatch(UUID_PATTERN, run_id):
            raise SandboxError("run_id inválido")
        path = self._root / run_id
        if path.is_symlink() or path.resolve().parent != self._root:
            raise SandboxError("destino fuera del sandbox")
        return path

    def _read_marker(self, path: Path, run_id: str) -> dict[str, str]:
        marker_path = path / MARKER_NAME
        if not marker_path.is_file():
            raise SandboxError("el directorio no es un sandbox de WALLBA")
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("label") != MARKER_LABEL or marker.get("run_id") != run_id:
            raise SandboxError("el marcador del sandbox no coincide")
        return marker

    def _write_marker(self, path: Path, run_id: str, fixture: Fixture) -> None:
        marker = {
            "label": MARKER_LABEL,
            "run_id": run_id,
            "side": self._side,
            "fixture_digest": fixture_digest(fixture),
        }
        (path / MARKER_NAME).write_text(json.dumps(marker), encoding="utf-8")

    def _write_files(self, path: Path, fixture: Fixture) -> None:
        for name, content in fixture.files:
            target = path / "files" / name
            target.write_bytes(content.encode("utf-8"))
            target.chmod(stat.S_IREAD)

    def _open_sandbox(self, run_id: str, path: Path, digest: str) -> Sandbox:
        sandbox = Sandbox(
            run_id=run_id,
            path=path,
            engine=create_sqlite_engine(path / DB_NAME),
            fixture_digest=digest,
        )
        self._open[run_id] = sandbox
        return sandbox

    def _seed_database(self, sandbox: Sandbox, fixture: Fixture) -> None:
        with write_transaction(sandbox.engine) as connection:
            for statement in SCHEMA:
                connection.execute(text(statement))
            for record in fixture.records:
                connection.execute(
                    text(
                        "INSERT INTO demo_records (id, tenant_marker, label, version) "
                        "VALUES (:id, :tenant, :label, 1)"
                    ),
                    {"id": record.id, "tenant": sandbox.run_id, "label": record.label},
                )
            for resource_id, version in INITIAL_RESOURCE_VERSIONS.items():
                connection.execute(
                    text("INSERT INTO resource_versions (resource_id, version) VALUES (:id, :version)"),
                    {"id": resource_id, "version": version},
                )


def _force_remove(function, path, _exc) -> None:
    """Los fixtures son de solo lectura: se habilita escritura solo para borrarlos."""
    Path(path).chmod(stat.S_IWRITE)
    function(path)
