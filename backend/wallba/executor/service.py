"""Servicio ejecutor protegido y harness baseline inseguro.

El protegido nunca decide política: valida la capacidad y aplica el efecto y el
receipt en una sola transacción local. El baseline carece de autoridad y solo
existe para comparar dentro del laboratorio.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable

from sqlalchemy import Connection, text

from wallba.contracts.canonical import CanonicalRequest, canonical_json, sha256_hex
from wallba.contracts.capability import Capability
from wallba.contracts.decision import ExecutionReceipt
from wallba.contracts.results import ToolResult
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER, ToolCall
from wallba.executor import journal
from wallba.executor.capabilities import CapabilityVerifier, Clock, utc_now
from wallba.executor.errors import CapabilityRejected, ToolError
from wallba.executor.runtime import ExecutorRuntime
from wallba.executor.sandbox import Sandbox
from wallba.executor.tools import ToolContext, ToolOutcome, dispatch
from wallba.foundation.database import write_transaction

FaultHook = Callable[[str], None]


def _no_fault(_point: str) -> None:
    return None


def current_resource_version(connection: Connection, resource_id: str) -> int | None:
    return connection.execute(
        text("SELECT version FROM resource_versions WHERE resource_id = :id"), {"id": resource_id}
    ).scalar_one_or_none()


def _bump_resource_version(connection: Connection, resource_id: str) -> None:
    connection.execute(
        text("UPDATE resource_versions SET version = version + 1 WHERE resource_id = :id"),
        {"id": resource_id},
    )


def _run_tool(call: ToolCall, execution_id: str, sandbox: Sandbox, connection: Connection) -> ToolOutcome:
    context = ToolContext(
        connection=connection,
        execution_id=execution_id,
        tenant_marker=sandbox.run_id,
        files_dir=sandbox.files_dir,
    )
    outcome = dispatch(call, context)
    if outcome.effect_count > 0:
        _bump_resource_version(connection, call.resource_id)
    return outcome


class ExecutorService:
    def __init__(
        self,
        runtime: ExecutorRuntime,
        verifier: CapabilityVerifier,
        clock: Clock = utc_now,
        fault: FaultHook = _no_fault,
    ) -> None:
        self._runtime = runtime
        self._verifier = verifier
        self._clock = clock
        self._fault = fault

    def execute(self, request: CanonicalRequest, capability: Capability) -> ExecutionReceipt:
        self._verifier.verify(request, capability)
        call = TOOL_CALL_ADAPTER.validate_python(request.call.model_dump(mode="python"))
        digest = request.digest()
        nonce_hash = sha256_hex(capability.nonce.encode("utf-8"))

        # En este orden: si otra llamada confirma entre ambas lecturas, su entrada ya es visible.
        nonce_seen = self._runtime.nonce_seen(nonce_hash)
        previous = self._runtime.find_entry(capability.execution_id)
        if previous is not None:
            return self._same_or_replay(previous, digest, nonce_hash)
        if nonce_seen:
            raise CapabilityRejected("NONCE_REPLAY")

        sandbox = self._runtime.active()
        try:
            with write_transaction(sandbox.engine) as connection:
                # Dentro de la transacción: dos llamadas concurrentes se serializan aquí.
                raced = journal.find_by_execution(connection, capability.execution_id)
                if raced is not None:
                    return self._same_or_replay(raced, digest, nonce_hash)
                if journal.nonce_exists(connection, nonce_hash):
                    raise CapabilityRejected("NONCE_REPLAY")
                if current_resource_version(connection, call.resource_id) != request.resource_version:
                    raise CapabilityRejected("STALE_RESOURCE")
                outcome = _run_tool(call, capability.execution_id, sandbox, connection)
                receipt = self._record(connection, capability, call, digest, nonce_hash, outcome)
                self._fault("before_commit")
        except ToolError:
            # La transacción ya revirtió: el fallo se registra sin efecto.
            with write_transaction(sandbox.engine) as connection:
                receipt = self._record(connection, capability, call, digest, nonce_hash, None)
        self._fault("after_commit")
        return receipt

    def receipt(self, execution_id: str) -> ExecutionReceipt | None:
        entry = self._runtime.find_entry(execution_id)
        return entry.receipt if entry else None

    def result(self, execution_id: str) -> ToolResult | None:
        entry = self._runtime.find_entry(execution_id)
        return entry.result if entry else None

    def resource_version(self, resource_id: str) -> int | None:
        with self._runtime.active().engine.connect() as connection:
            return current_resource_version(connection, resource_id)

    def _record(
        self,
        connection: Connection,
        capability: Capability,
        call: ToolCall,
        digest: str,
        nonce_hash: str,
        outcome: ToolOutcome | None,
    ) -> ExecutionReceipt:
        return journal.record(
            connection,
            execution_id=capability.execution_id,
            nonce_hash=nonce_hash,
            request_id=call.request_id,
            request_digest=digest,
            state="SUCCEEDED" if outcome is not None else "FAILED",
            result=outcome.result if outcome is not None else None,
            effect_count=outcome.effect_count if outcome is not None else 0,
            completed_at=self._clock(),
        )

    @staticmethod
    def _same_or_replay(entry: journal.JournalEntry, digest: str, nonce_hash: str) -> ExecutionReceipt:
        # Un nonce o execution_id ajeno nunca recibe el receipt de otra carga.
        if entry.request_digest != digest or entry.nonce_hash != nonce_hash:
            raise CapabilityRejected("NONCE_REPLAY")
        return entry.receipt


class BaselineExecutor:
    """Harness inseguro del laboratorio: ejecuta sin capacidad sobre su propio sandbox."""

    def __init__(self, runtime: ExecutorRuntime, clock: Clock = utc_now) -> None:
        self._runtime = runtime
        self._clock = clock

    def execute(self, call: ToolCall) -> ExecutionReceipt:
        sandbox = self._runtime.active()
        execution_id = str(uuid.uuid4())
        digest = sha256_hex(canonical_json(TOOL_CALL_ADAPTER.dump_python(call, mode="json")))
        nonce_hash = sha256_hex(secrets.token_hex(16).encode("utf-8"))
        try:
            with write_transaction(sandbox.engine) as connection:
                outcome = _run_tool(call, execution_id, sandbox, connection)
                return journal.record(
                    connection,
                    execution_id=execution_id,
                    nonce_hash=nonce_hash,
                    request_id=call.request_id,
                    request_digest=digest,
                    state="SUCCEEDED",
                    result=outcome.result,
                    effect_count=outcome.effect_count,
                    completed_at=self._clock(),
                )
        except ToolError:
            with write_transaction(sandbox.engine) as connection:
                return journal.record(
                    connection,
                    execution_id=execution_id,
                    nonce_hash=nonce_hash,
                    request_id=call.request_id,
                    request_digest=digest,
                    state="FAILED",
                    result=None,
                    effect_count=0,
                    completed_at=self._clock(),
                )
