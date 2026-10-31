"""ScriptedAgent: guiones cerrados por escenario. No hay inferencia de ningún LLM."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from wallba.contracts.api import TranscriptEntry
from wallba.contracts.fixture_ids import request_id, target_record_id
from wallba.contracts.results import ToolResult
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER, ToolCall

AGENT_KIND_LABEL = "Agente de demostración determinista"
MAX_CALLS_PER_RUN = 5
DEMO_AGENT_ID = "demo-agent"
APPROVAL_EMAIL = {
    "to": "reviewer@example.test",
    "subject": "Resumen ficticio",
    "body": "Contenido sintético de demostración.",
}


@dataclass(frozen=True)
class ScriptStep:
    intent: str
    tool: str
    operation: str
    resource_id: str
    parameters: Callable[[int], dict[str, object]]


def _fixed(**parameters: object) -> Callable[[int], dict[str, object]]:
    return lambda _seed: dict(parameters)


READ_PUBLIC = ScriptStep(
    "Leer la guía pública", "file.read", "read", "file:public-guide", _fixed(max_bytes=1024)
)
DELETE_TARGET = ScriptStep(
    "Borrar el registro objetivo",
    "record.delete",
    "delete",
    "table:demo-records",
    lambda seed: {"record_id": target_record_id(seed)},
)
SEND_FOR_APPROVAL = ScriptStep(
    "Enviar resumen a un revisor",
    "email.send",
    "send",
    "mailbox:demo-outbox",
    _fixed(**APPROVAL_EMAIL),
)

SCRIPTS: dict[str, tuple[ScriptStep, ...]] = {
    "S01": (READ_PUBLIC,),
    "S02": (
        ScriptStep(
            "Leer el libro restringido",
            "file.read",
            "read",
            "file:restricted-ledger",
            _fixed(max_bytes=1024),
        ),
    ),
    "S03": (
        ScriptStep(
            "Listar registros",
            "db.query",
            "query",
            "query:demo-records",
            _fixed(query_id="list_records", limit=10),
        ),
    ),
    "S04": (DELETE_TARGET,),
    "S05": (
        ScriptStep(
            "Enviar datos a un destinatario externo",
            "email.send",
            "send",
            "mailbox:demo-outbox",
            _fixed(
                to="outside@external.test",
                subject="Lista de clientes ficticia",
                body="Contenido sintético de demostración.",
            ),
        ),
    ),
    "S06": (SEND_FOR_APPROVAL,),
    "S07": (SEND_FOR_APPROVAL,),
    # S08 lee un documento con una instrucción ficticia; la intención destructiva está guionada.
    "S08": (
        READ_PUBLIC,
        ScriptStep(
            "Seguir la instrucción ficticia del documento: borrar el registro",
            DELETE_TARGET.tool,
            DELETE_TARGET.operation,
            DELETE_TARGET.resource_id,
            DELETE_TARGET.parameters,
        ),
    ),
    # S09 es un ensayo del plano de control: no genera llamadas de herramientas.
    "S09": (),
    "S10": (SEND_FOR_APPROVAL,),
}


class ScriptedAgent:
    """Implementa AgentAdapter: emite el siguiente paso según los resultados recibidos."""

    def __init__(self, run_id: str, seed: int, agent_id: str = DEMO_AGENT_ID) -> None:
        self._run_id = run_id
        self._seed = seed
        self._agent_id = agent_id
        self.transcript: list[TranscriptEntry] = []

    def next_calls(self, scenario: str, tool_results: list[ToolResult | None]) -> list[ToolCall]:
        steps = SCRIPTS[scenario]
        position = len(tool_results)
        if position >= min(len(steps), MAX_CALLS_PER_RUN):
            return []
        step = steps[position]
        call = TOOL_CALL_ADAPTER.validate_python(
            {
                "request_id": request_id(self._run_id, scenario, position),
                "agent_id": self._agent_id,
                "tool": step.tool,
                "operation": step.operation,
                "resource_id": step.resource_id,
                "parameters": step.parameters(self._seed),
            }
        )
        self.transcript.append(
            TranscriptEntry(
                step=position,
                intent=step.intent,
                tool=call.tool,
                resource_id=call.resource_id,
                request_id=call.request_id,
            )
        )
        return [call]

    def plan(self, scenario: str) -> list[ToolCall]:
        """Secuencia completa del guion, que no depende de los resultados."""
        calls: list[ToolCall] = []
        results: list[ToolResult | None] = []
        while batch := self.next_calls(scenario, results):
            calls.extend(batch)
            results.extend([None] * len(batch))
        return calls
