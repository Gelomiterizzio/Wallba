"""file.read: solo recursos del catálogo, nunca rutas de la solicitud."""

from __future__ import annotations

from wallba.contracts.canonical import sha256_hex
from wallba.contracts.results import FileReadResult
from wallba.contracts.tool_call import FileReadCall
from wallba.demo.fixtures import FILE_CATALOG, PUBLIC_RESOURCES
from wallba.executor.errors import ToolError
from wallba.executor.tools.base import ToolContext, ToolOutcome


def run_file_read(call: FileReadCall, context: ToolContext) -> ToolOutcome:
    name = FILE_CATALOG.get(call.resource_id)
    if name is None:
        raise ToolError("UNKNOWN_RESOURCE")
    path = context.files_dir / name
    if path.is_symlink() or not path.is_file():
        raise ToolError("RESOURCE_UNAVAILABLE")
    if path.resolve().parent != context.files_dir.resolve():
        raise ToolError("RESOURCE_UNAVAILABLE")

    with path.open("rb") as handle:
        data = handle.read(call.parameters.max_bytes)
    # Del recurso restringido solo salen digest y longitud.
    content = data.decode("utf-8", errors="replace") if call.resource_id in PUBLIC_RESOURCES else None
    result = FileReadResult(content=content, content_digest=sha256_hex(data), bytes=len(data))
    return ToolOutcome(result=result, effect_count=0)
