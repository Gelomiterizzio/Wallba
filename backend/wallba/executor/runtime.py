"""Estado del proceso ejecutor: entorno activo y búsqueda duradera de receipts."""

from __future__ import annotations

import uuid
from pathlib import Path

from wallba.executor.journal import JournalEntry, find_by_execution, nonce_exists
from wallba.executor.sandbox import Sandbox, SandboxError, SandboxManager

ACTIVE_FILE = "active-run"
# Entorno inicial estable: permite probar el puerto sin que exista una demo.
DEFAULT_RUN_ID = str(uuid.UUID("00000000-0000-4000-8000-000000000001"))
DEFAULT_SEED = 0


class ExecutorRuntime:
    def __init__(self, root: Path, side: str) -> None:
        self._root = root
        root.mkdir(parents=True, exist_ok=True)
        self.sandboxes = SandboxManager(root, side)

    def active(self) -> Sandbox:
        marker = self._root / ACTIVE_FILE
        if marker.is_file():
            return self.sandboxes.get(marker.read_text(encoding="utf-8").strip())
        return self.activate(DEFAULT_RUN_ID, DEFAULT_SEED)

    def activate(self, run_id: str, seed: int) -> Sandbox:
        """Crea el sandbox si falta y lo deja activo; sobrevive a un reinicio."""
        try:
            sandbox = self.sandboxes.get(run_id)
        except SandboxError:
            sandbox = self.sandboxes.prepare(run_id, seed)
        (self._root / ACTIVE_FILE).write_text(run_id, encoding="utf-8")
        return sandbox

    def reset(self, run_id: str) -> None:
        if self.active().run_id == run_id:
            raise SandboxError("no se puede reiniciar el entorno activo")
        self.sandboxes.reset(run_id)

    def find_entry(self, execution_id: str) -> JournalEntry | None:
        for run_id in self.sandboxes.run_ids():
            with self.sandboxes.get(run_id).engine.connect() as connection:
                entry = find_by_execution(connection, execution_id)
            if entry is not None:
                return entry
        return None

    def nonce_seen(self, nonce_hash: str) -> bool:
        """Un nonce no se reutiliza ni entre entornos de runs distintos."""
        for run_id in self.sandboxes.run_ids():
            with self.sandboxes.get(run_id).engine.connect() as connection:
                if nonce_exists(connection, nonce_hash):
                    return True
        return False
