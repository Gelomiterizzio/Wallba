"""ToolCall: unión discriminada cerrada por `tool`.

Cada herramienta fija su `operation`, sus `resource_id` admitidos y sus
parámetros exactos. Campos de autoridad (principal, roles, entorno, riesgo,
hora) no existen aquí: el servidor los deriva.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, TypeAdapter

from wallba.contracts.common import Identifier, SafeText, StrictModel, Uuid

ToolName = Literal["file.read", "email.send", "record.delete", "db.query"]


class FileReadParams(StrictModel):
    max_bytes: int = Field(ge=1, le=16384)


class EmailSendParams(StrictModel):
    to: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.test$")
    subject: SafeText = Field(max_length=120)
    body: SafeText = Field(max_length=4096)


class RecordDeleteParams(StrictModel):
    record_id: Uuid


class DbQueryParams(StrictModel):
    query_id: Literal["list_records", "count_records"]
    limit: int = Field(ge=1, le=100)


class ToolCallBase(StrictModel):
    request_id: Uuid
    agent_id: Identifier


class FileReadCall(ToolCallBase):
    tool: Literal["file.read"]
    operation: Literal["read"]
    resource_id: Literal["file:public-guide", "file:restricted-ledger"]
    parameters: FileReadParams


class EmailSendCall(ToolCallBase):
    tool: Literal["email.send"]
    operation: Literal["send"]
    resource_id: Literal["mailbox:demo-outbox"]
    parameters: EmailSendParams


class RecordDeleteCall(ToolCallBase):
    tool: Literal["record.delete"]
    operation: Literal["delete"]
    resource_id: Literal["table:demo-records"]
    parameters: RecordDeleteParams


class DbQueryCall(ToolCallBase):
    tool: Literal["db.query"]
    operation: Literal["query"]
    resource_id: Literal["query:demo-records"]
    parameters: DbQueryParams


ToolCall = Annotated[
    Union[FileReadCall, EmailSendCall, RecordDeleteCall, DbQueryCall],
    Field(discriminator="tool"),
]
TOOL_CALL_ADAPTER: TypeAdapter[ToolCall] = TypeAdapter(ToolCall)
