"""Persona 3 human decisions, integrity checks and atomic approval consumption."""

from datetime import timedelta

from sqlalchemy import select, update

from wallba.approvals.models import approvals
from wallba.auth.schema import principals, sessions
from wallba.contracts.canonical import CanonicalRequest, canonical_json
from wallba.contracts.ports import Principal
from wallba.foundation.database import write_transaction
from wallba.foundation.http import ApiError, decode_cursor, encode_cursor
from wallba.gateway.identity import refresh_identity
from wallba.gateway.repository import (
    canonical_from,
    instant,
    request_row,
    set_state,
    stamp,
    view_of,
)


class ApprovalService:
    def __init__(self, gateway):
        self.gateway = gateway
        self.engine = gateway.engine

    def _actor(self, connection, actor, *, role=None, session_hash=None):
        row = (
            connection.execute(
                select(principals).where(
                    principals.c.id == actor.principal_id,
                    principals.c.kind == "human",
                    principals.c.disabled.is_(False),
                )
            )
            .mappings()
            .first()
            if actor.kind == "human"
            else None
        )
        if row is None or (role is not None and role not in row["roles_json"]):
            raise ApiError(403, "ROLE_DENIED", "Permiso humano insuficiente")
        if session_hash is not None:
            session = (
                connection.execute(
                    select(sessions).where(
                        sessions.c.token_hash == session_hash,
                        sessions.c.principal_id == actor.principal_id,
                        sessions.c.revoked_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
            now = self.gateway._now()
            if (
                session is None
                or now >= instant(session["expires_at"])
                or now >= instant(session["last_seen_at"]) + timedelta(minutes=30)
            ):
                raise ApiError(
                    401, "AUTHENTICATION_REQUIRED", "Sesión revocada o expirada"
                )
        return Principal(
            principal_id=actor.principal_id, kind="human", roles=row["roles_json"]
        )

    @staticmethod
    def _row(connection, approval_id):
        row = (
            connection.execute(
                select(approvals).where(approvals.c.approval_id == approval_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ApiError(404, "NOT_FOUND", "Aprobación no encontrada")
        return row

    def _expire(self, connection, approval, request, reason):
        connection.execute(
            update(approvals)
            .where(
                approvals.c.approval_id == approval["approval_id"],
                approvals.c.status.in_(["PENDING", "APPROVED"]),
            )
            .values(
                status="EXPIRED",
                row_version=approvals.c.row_version + 1,
                reason_code=reason,
                decided_at=stamp(self.gateway._now()),
            )
        )
        set_state(connection, request["request_id"], "EXPIRED")
        self.gateway._event(
            connection,
            "approval_expired",
            request,
            approval_id=approval["approval_id"],
            reason_code=reason,
            status="EXPIRED",
        )

    def _expire_due(self, connection, approval):
        if approval["status"] in {
            "PENDING",
            "APPROVED",
        } and self.gateway._now() >= instant(approval["expires_at"]):
            self._expire(
                connection,
                approval,
                request_row(connection, approval["request_id"]),
                "APPROVAL_EXPIRED",
            )
            return self._row(connection, approval["approval_id"])
        return approval

    def _detail(self, connection, approval):
        request = request_row(connection, approval["request_id"])
        view = view_of(connection, request)
        decision = view.decision
        return {
            "approval_id": approval["approval_id"],
            "request_id": approval["request_id"],
            "status": approval["status"],
            "row_version": approval["row_version"],
            "principal_id": request["principal_id"],
            "agent_id": request["agent_id"],
            "snapshot": approval["snapshot_json"],
            "request_digest": approval["request_digest"],
            "policy_id": approval["policy_id"],
            "policy_version": approval["policy_version"],
            "risk": decision.risk,
            "created_at": approval["created_at"],
            "expires_at": approval["expires_at"],
            "approver_id": approval["approver_id"],
            "reason": approval["reason"],
            "reason_code": approval["reason_code"],
            "decided_at": approval["decided_at"],
            "request_state": view.state,
            "execution_id": view.execution_id,
            "receipt": view.receipt.model_dump(mode="json") if view.receipt else None,
        }

    def get(self, approval_id, actor):
        with write_transaction(self.engine) as connection:
            self._actor(connection, actor, role="viewer")
            return self._detail(
                connection,
                self._expire_due(connection, self._row(connection, approval_id)),
            )

    def list(
        self, actor, *, status=None, agent_id=None, risk=None, cursor=None, limit=50
    ):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ApiError(422, "VALIDATION_ERROR", "Límite inválido")
        allowed = {
            "PENDING",
            "APPROVED",
            "CONSUMED",
            "REJECTED",
            "EXPIRED",
            "CANCELLED",
        }
        if status is not None and status not in allowed:
            raise ApiError(422, "VALIDATION_ERROR", "Estado inválido")
        if risk is not None and risk not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ApiError(422, "VALIDATION_ERROR", "Riesgo inválido")
        with write_transaction(self.engine) as connection:
            self._actor(connection, actor, role="viewer")
            # Expiration is authoritative on every action, even without a worker.
            due = (
                connection.execute(
                    select(approvals).where(
                        approvals.c.status.in_(["PENDING", "APPROVED"]),
                        approvals.c.expires_at <= stamp(self.gateway._now()),
                    )
                )
                .mappings()
                .all()
            )
            for approval in due:
                self._expire(
                    connection,
                    approval,
                    request_row(connection, approval["request_id"]),
                    "APPROVAL_EXPIRED",
                )
            query = select(approvals).order_by(
                approvals.c.created_at.desc(), approvals.c.approval_id.desc()
            )
            if status:
                query = query.where(approvals.c.status == status)
            if agent_id:
                from wallba.gateway.schema import requests

                query = query.join(requests).where(requests.c.agent_id == agent_id)
            if cursor:
                decoded = decode_cursor(cursor)
                try:
                    created, identifier = decoded.rsplit("|", 1)
                    instant(created)
                    from uuid import UUID

                    UUID(identifier)
                except ValueError as exc:
                    raise ApiError(422, "VALIDATION_ERROR", "Cursor inválido") from exc
                query = query.where(
                    (approvals.c.created_at < created)
                    | (
                        (approvals.c.created_at == created)
                        & (approvals.c.approval_id < identifier)
                    )
                )
            # Risk is a stored server decision; never infer it from UI labels.
            found = []
            for approval in connection.execute(query).mappings():
                detail = self._detail(connection, approval)
                if risk is None or detail["risk"] == risk:
                    found.append(detail)
                if len(found) > limit:
                    break
            page = found[:limit]
            next_cursor = (
                encode_cursor(page[-1]["created_at"] + "|" + page[-1]["approval_id"])
                if len(found) > limit
                else None
            )
            return {"items": page, "next_cursor": next_cursor}

    def resolve(
        self, approval_id, actor, action, expected_version, reason, *, session_hash=None
    ):
        if (
            action not in {"approve", "reject", "cancel"}
            or type(expected_version) is not int
            or expected_version < 1
        ):
            raise ApiError(422, "VALIDATION_ERROR", "Acción o versión inválida")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise ApiError(
                422, "VALIDATION_ERROR", "Indica un motivo de 1 a 500 caracteres"
            )
        from wallba.contracts.common import ensure_safe_text

        try:
            ensure_safe_text(reason)
        except ValueError as exc:
            raise ApiError(422, "VALIDATION_ERROR", "Motivo no válido") from exc
        # Fetch only resource metadata before entering the writer transaction.
        # Expired/cancelled requests do not need a reachable executor to reject.
        resource_version = None
        if action == "approve":
            with self.engine.connect() as connection:
                self._actor(
                    connection, actor, role="approver", session_hash=session_hash
                )
                ap = self._row(connection, approval_id)
                row = request_row(connection, ap["request_id"])
                pending = ap["status"] == "PENDING" and self.gateway._now() < instant(
                    ap["expires_at"]
                )
                if pending and actor.principal_id != row["principal_id"]:
                    canonical = canonical_from(row)
                else:
                    canonical = None
            if canonical is not None:
                resource_version = self.gateway._version(canonical.call.resource_id)
        failure = None
        claim = None
        with write_transaction(self.engine) as connection:
            actor = self._actor(
                connection,
                actor,
                role="approver" if action != "cancel" else None,
                session_hash=session_hash,
            )
            approval = self._row(connection, approval_id)
            row = request_row(connection, approval["request_id"])
            if action == "cancel" and not (
                "approver" in actor.roles
                or (
                    "operator" in actor.roles
                    and actor.principal_id == row["principal_id"]
                )
            ):
                raise ApiError(403, "ROLE_DENIED", "No puedes cancelar esta solicitud")
            if action == "approve" and actor.principal_id == row["principal_id"]:
                raise ApiError(
                    403,
                    "SELF_APPROVAL_DENIED",
                    "El solicitante no puede aprobar su propia operación",
                )
            approval = self._expire_due(connection, approval)
            if approval["status"] == "EXPIRED":
                failure = ApiError(
                    410,
                    approval["reason_code"] or "APPROVAL_EXPIRED",
                    "La aprobación ha expirado",
                )
            elif approval["status"] != "PENDING":
                code = (
                    "APPROVAL_ALREADY_CONSUMED"
                    if approval["status"] == "CONSUMED"
                    else "APPROVAL_STATE_CONFLICT"
                )
                failure = ApiError(409, code, "La aprobación ya no está pendiente")
            elif approval["row_version"] != expected_version:
                failure = ApiError(
                    409,
                    "APPROVAL_VERSION_CONFLICT",
                    "Actualiza la aprobación antes de actuar",
                )
            elif action != "approve":
                status = "REJECTED" if action == "reject" else "CANCELLED"
                changed = connection.execute(
                    update(approvals)
                    .where(
                        approvals.c.approval_id == approval_id,
                        approvals.c.status == "PENDING",
                        approvals.c.row_version == expected_version,
                    )
                    .values(
                        status=status,
                        row_version=expected_version + 1,
                        approver_id=actor.principal_id,
                        reason=reason,
                        decided_at=stamp(self.gateway._now()),
                    )
                )
                if changed.rowcount != 1:
                    raise ApiError(
                        409, "APPROVAL_VERSION_CONFLICT", "La aprobación cambió"
                    )
                set_state(connection, row["request_id"], status)
                self.gateway._event(
                    connection,
                    "approval_rejected" if action == "reject" else "approval_cancelled",
                    row,
                    principal_id=actor.principal_id,
                    approval_id=approval_id,
                    status=status,
                )
            else:
                try:
                    canonical = canonical_from(row)
                    approved_snapshot = CanonicalRequest.model_validate(
                        approval["snapshot_json"]
                    )
                    if (
                        approved_snapshot.digest() != approval["request_digest"]
                        or canonical.digest() != approval["request_digest"]
                        or canonical_json(approved_snapshot.model_dump(mode="json"))
                        != canonical.canonical_bytes()
                    ):
                        raise ApiError(
                            409, "DIGEST_MISMATCH", "El snapshot fue modificado"
                        )
                    if self.gateway._active_run(connection) != row["demo_run_id"]:
                        raise ApiError(
                            409, "STALE_RESOURCE", "El entorno de demostración cambió"
                        )
                    requester = refresh_identity(
                        connection,
                        Principal(
                            principal_id=row["principal_id"],
                            kind=row["principal_kind"],
                            roles=[],
                        ),
                        canonical.call,
                        row["credential_hash"],
                    )
                    snapshot, decision = self.gateway._snapshot_decision(
                        connection, canonical, requester
                    )
                    if snapshot is None or (
                        snapshot.document.policy_id,
                        snapshot.document.version,
                        snapshot.checksum,
                    ) != (
                        approval["policy_id"],
                        approval["policy_version"],
                        approval["policy_checksum"],
                    ):
                        raise ApiError(
                            409, "STALE_POLICY", "La política cambió desde la solicitud"
                        )
                    if decision.decision != "REQUIRE_APPROVAL":
                        raise ApiError(
                            403, "SCOPE_DENIED", "La autorización ya no es válida"
                        )
                    if resource_version != canonical.resource_version:
                        raise ApiError(
                            409,
                            "STALE_RESOURCE",
                            "El recurso cambió desde la solicitud",
                        )
                except ApiError as exc:
                    self._expire(connection, approval, row, exc.code)
                    failure = exc
                except (ValueError, TypeError, UnicodeError, RecursionError):
                    self._expire(connection, approval, row, "DIGEST_MISMATCH")
                    failure = ApiError(
                        409, "DIGEST_MISMATCH", "El snapshot fue modificado"
                    )
                if failure is None:
                    changed = connection.execute(
                        update(approvals)
                        .where(
                            approvals.c.approval_id == approval_id,
                            approvals.c.status == "PENDING",
                            approvals.c.row_version == expected_version,
                        )
                        .values(
                            status="APPROVED",
                            row_version=expected_version + 1,
                            approver_id=actor.principal_id,
                            reason=reason,
                            decided_at=stamp(self.gateway._now()),
                        )
                    )
                    if changed.rowcount != 1:
                        raise ApiError(
                            409, "APPROVAL_VERSION_CONFLICT", "La aprobación cambió"
                        )
                    self.gateway._event(
                        connection,
                        "approval_approved",
                        row,
                        principal_id=actor.principal_id,
                        approval_id=approval_id,
                        status="APPROVED",
                    )
                    claim = self.gateway.claim(connection, row, canonical, decision)
                    connection.execute(
                        update(approvals)
                        .where(approvals.c.approval_id == approval_id)
                        .values(
                            status="CONSUMED",
                            row_version=expected_version + 2,
                            consumed_at=stamp(self.gateway._now()),
                        )
                    )
                    self.gateway._event(
                        connection,
                        "approval_consumed",
                        row,
                        principal_id=actor.principal_id,
                        approval_id=approval_id,
                        status="CONSUMED",
                    )
            detail = self._detail(connection, self._row(connection, approval_id))
        if failure:
            raise failure
        if claim:
            self.gateway.dispatch(row["request_id"], *claim)
            with self.engine.connect() as connection:
                detail = self._detail(connection, self._row(connection, approval_id))
        return detail
