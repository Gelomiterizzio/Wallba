"""Resultados saneados de las cuatro herramientas."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, TypeAdapter

from wallba.contracts.common import Sha256Hex, StrictModel, Uuid


class FileReadResult(StrictModel):
    tool: Literal["file.read"] = "file.read"
    # Null para recursos restringidos: solo se expone digest y longitud.
    content: str | None
    content_digest: Sha256Hex
    bytes: int = Field(ge=0, le=16384)


class EmailSendResult(StrictModel):
    tool: Literal["email.send"] = "email.send"
    message_id: Uuid
    delivery: Literal["SIMULATED"] = "SIMULATED"


class RecordDeleteResult(StrictModel):
    tool: Literal["record.delete"] = "record.delete"
    deleted_count: int = Field(ge=0, le=1)


class RecordRow(StrictModel):
    id: Uuid
    label: str


class DbQueryResult(StrictModel):
    tool: Literal["db.query"] = "db.query"
    rows: list[RecordRow] | None
    count: int | None = Field(ge=0)


ToolResult = Annotated[
    Union[FileReadResult, EmailSendResult, RecordDeleteResult, DbQueryResult],
    Field(discriminator="tool"),
]
TOOL_RESULT_ADAPTER: TypeAdapter[ToolResult] = TypeAdapter(ToolResult)
