"""Catálogo de agentes y runs de agente persistidos en la base de control."""

from __future__ import annotations

import uuid

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from wallba.agent.scripted import AGENT_KIND_LABEL, DEMO_AGENT_ID, ScriptedAgent
from wallba.contracts.api import AgentDetail, AgentRunAccepted, AgentRunView, AgentSummary, TranscriptEntry
from wallba.contracts.common import UtcDatetime
from wallba.contracts.ports import Principal, ToolGateway
from wallba.foundation.clock import utc_now
from wallba.foundation.database import write_transaction
from wallba.foundation.models import AgentRow, AgentRunRow

ALL_TOOLS = ["db.query", "email.send", "file.read", "record.delete"]
ALL_RESOURCES = [
    "file:public-guide",
    "file:restricted-ledger",
    "mailbox:demo-outbox",
    "query:demo-records",
    "table:demo-records",
]
AGENT_SEED = (
    (DEMO_AGENT_ID, "Agente de demostración", ALL_TOOLS, ALL_RESOURCES),
    ("scoped-reader", "Lector con alcance reducido", ["file.read"], ["file:public-guide"]),
)


def seed_agents(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        for agent_id, name, tools, scopes in AGENT_SEED:
            if session.get(AgentRow, agent_id) is None:
                session.add(
                    AgentRow(
                        id=agent_id,
                        name=name,
                        tools_json=tools,
                        resource_scopes_json=scopes,
                        status="ACTIVE",
                    )
                )


def _summary(row: AgentRow) -> AgentSummary:
    return AgentSummary(id=row.id, name=row.name, tools=row.tools_json, status=row.status)


def list_agents(engine: Engine) -> list[AgentSummary]:
    with Session(engine) as session:
        rows = session.scalars(select(AgentRow).order_by(AgentRow.id.desc())).all()
        return [_summary(row) for row in rows]


def get_agent(engine: Engine, agent_id: str) -> AgentDetail | None:
    with Session(engine) as session:
        row = session.get(AgentRow, agent_id)
        if row is None:
            return None
        return AgentDetail(
            **_summary(row).model_dump(),
            resource_scopes=row.resource_scopes_json,
            kind_label=AGENT_KIND_LABEL,
        )


class AgentRunService:
    def __init__(self, engine: Engine, gateway: ToolGateway) -> None:
        self._engine = engine
        self._gateway = gateway

    def create(self, scenario_id: str, principal: Principal) -> AgentRunAccepted:
        run_id = str(uuid.uuid4())
        created_at: UtcDatetime = utc_now()
        with write_transaction(self._engine) as connection:
            with Session(bind=connection) as session:
                session.add(
                    AgentRunRow(
                        run_id=run_id,
                        agent_id=DEMO_AGENT_ID,
                        scenario_id=scenario_id,
                        status="RUNNING",
                        request_ids_json=[],
                        transcript_json=[],
                        created_by=principal.principal_id,
                        created_at=created_at,
                    )
                )
                session.flush()
        return AgentRunAccepted(run_id=run_id, status="RUNNING")

    def execute(self, run_id: str, scenario_id: str, seed: int, principal: Principal) -> None:
        """Las llamadas salen solo por el gateway; un fallo queda registrado como FAILED."""
        agent = ScriptedAgent(run_id, seed)
        request_ids: list[str] = []
        status = "COMPLETED"
        try:
            for call in agent.plan(scenario_id):
                key = str(uuid.uuid5(uuid.UUID(call.request_id), "idempotency"))
                self._gateway.submit(call, principal, key)
                request_ids.append(call.request_id)
        except Exception:  # noqa: BLE001 - el motivo se conserva en el estado del run
            status = "FAILED"
        self._finish(run_id, status, request_ids, agent.transcript)

    def _finish(
        self, run_id: str, status: str, request_ids: list[str], transcript: list[TranscriptEntry]
    ) -> None:
        with write_transaction(self._engine) as connection:
            with Session(bind=connection) as session:
                row = session.get(AgentRunRow, run_id)
                row.status = status
                row.request_ids_json = request_ids
                row.transcript_json = [entry.model_dump(mode="json") for entry in transcript]
                session.flush()

    def view(self, run_id: str) -> AgentRunView | None:
        with Session(self._engine) as session:
            row = session.get(AgentRunRow, run_id)
            if row is None:
                return None
            return AgentRunView(
                run_id=row.run_id,
                agent_id=row.agent_id,
                scenario_id=row.scenario_id,
                status=row.status,
                request_ids=row.request_ids_json,
                transcript=[TranscriptEntry.model_validate(entry) for entry in row.transcript_json],
                agent_kind_label=AGENT_KIND_LABEL,
            )
