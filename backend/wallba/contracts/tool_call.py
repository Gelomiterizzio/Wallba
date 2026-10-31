"""ToolCall: unión discriminada cerrada por `tool`.

Cada herramienta fija su `operation`, sus `resource_id` admitidos y sus
parámetros exactos. Campos de autoridad (principal, roles, entorno, riesgo,
hora) no existen aquí: el servidor los deriva.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, field_validator

from wallba.contracts.common import StrictModel, ensure_nfc

RequestId = Annotated[str, Field(min_length=1, max_length=64)]
AgentId = Annotated[str, Field(min_length=1, max_length=64)]


class FileReadParams(StrictModel):
    max_bytes: int = Field(ge=1, le=16384)


class EmailSendParams(StrictModel):
    to: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.test$")
    subject: str = Field(max_length=120)
    body: str = Field(max_length=4096)

    @field_validator("subject", "body")
    @classmethod
    def _nfc(cls, value: str, info) -> str:
        return ensure_nfc(value, info.field_name)


class RecordDeleteParams(StrictModel):
    record_id: str = Field(
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )


class DbQueryParams(StrictModel):
    query_id: Literal["list_records", "count_records"]
    limit: int = Field(ge=1, le=100)


class FileReadCall(StrictModel):
    request_id: RequestId
    agent_id: AgentId
    tool: Literal["file.read"]
    operation: Literal["read"]
    resource_id: Literal["file:public-guide", "file:restricted-ledger"]
    parameters: FileReadParams


class EmailSendCall(StrictModel):
    request_id: RequestId
    agent_id: AgentId
    tool: Literal["email.send"]
    operation: Literal["send"]
    resource_id: Literal["mailbox:demo-outbox"]
    parameters: EmailSendParams


class RecordDeleteCall(StrictModel):
    request_id: RequestId
    agent_id: AgentId
    tool: Literal["record.delete"]
    operation: Literal["delete"]
    resource_id: Literal["table:demo-records"]
    parameters: RecordDeleteParams


class DbQueryCall(StrictModel):
    request_id: RequestId
    agent_id: AgentId
    tool: Literal["db.query"]
    operation: Literal["query"]
    resource_id: Literal["query:demo-records"]
    parameters: DbQueryParams


ToolCall = Annotated[
    Union[FileReadCall, EmailSendCall, RecordDeleteCall, DbQueryCall],
    Field(discriminator="tool"),
]
