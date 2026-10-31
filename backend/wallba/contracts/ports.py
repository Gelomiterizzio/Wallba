"""Puertos compartidos. Solo firmas: sin imports de implementaciones.

Los tipos de RequestView, CanonicalRequest, Capability, DemoRun y
AuditEvent pertenecen a P3/P4/P1 y se añadirán tras su revisión; aquí se
usan sus nombres como anotaciones de cadena para no acoplar módulos.
"""

from __future__ import annotations

from typing import Any, Protocol

from wallba.contracts.decision import ExecutionReceipt
from wallba.contracts.tool_call import ToolCall


class AgentAdapter(Protocol):
    def next_calls(self, scenario: str, tool_results: list[Any]) -> list[ToolCall]: ...


class ToolGateway(Protocol):
    def submit(self, call: ToolCall, principal: Any, idempotency_key: str) -> Any: ...


class ExecutorPort(Protocol):
    def execute(self, canonical_request: Any, capability: Any) -> ExecutionReceipt: ...

    def receipt(self, execution_id: str) -> ExecutionReceipt | None: ...


class AuditSink(Protocol):
    def append(self, event: Any, transaction: Any) -> str: ...


class DemoRunner(Protocol):
    def run_pair(self, scenario_id: str, seed: int) -> Any: ...
