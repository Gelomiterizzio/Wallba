"""email.send: inserta en un outbox sintético. No existe cliente SMTP."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from wallba.contracts.canonical import sha256_hex
from wallba.contracts.results import EmailSendResult
from wallba.contracts.tool_call import EmailSendCall
from wallba.executor.tools.base import ToolContext, ToolOutcome


def run_email_send(call: EmailSendCall, context: ToolContext) -> ToolOutcome:
    message_id = str(uuid.uuid4())
    context.connection.execute(
        text(
            "INSERT INTO outbox (message_id, execution_id, to_address, subject, body_digest, status) "
            "VALUES (:message_id, :execution_id, :to_address, :subject, :body_digest, 'SIMULATED')"
        ),
        {
            "message_id": message_id,
            "execution_id": context.execution_id,
            "to_address": call.parameters.to,
            "subject": call.parameters.subject,
            "body_digest": sha256_hex(call.parameters.body.encode("utf-8")),
        },
    )
    return ToolOutcome(result=EmailSendResult(message_id=message_id), effect_count=1)
