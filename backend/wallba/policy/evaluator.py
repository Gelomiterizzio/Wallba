"""Evaluador puro. DENY > REQUIRE_APPROVAL > ALLOW. Sin IO ni reloj propio."""

from __future__ import annotations

from uuid import UUID

from pydantic import ValidationError

from wallba.policy.matchers import rule_matches
from wallba.policy.models import (
    NIL_REQUEST_ID,
    Decision,
    DecisionResult,
    EvaluationRequest,
    PolicyDocument,
    PolicySnapshot,
    ReasonCode,
    Risk,
    TrustedContext,
)
from wallba.policy.parameters import ParameterRejected, parse_parameters
from wallba.policy.risk import classify
from wallba.policy.schemas import document_checksum, validate_mapping


def evaluate(
    canonical_request: EvaluationRequest | dict[str, object],
    trusted_context: TrustedContext | dict[str, object],
    policy_snapshot: PolicySnapshot | None,
) -> DecisionResult:
    """Decide con el snapshot recibido. No busca otra política a mitad del cálculo."""

    request_id = _extract_request_id(canonical_request)
    try:
        return _evaluate(canonical_request, trusted_context, policy_snapshot, request_id)
    except Exception:
        return _closed(request_id, ReasonCode.AUTHORIZATION_UNAVAILABLE, Risk.HIGH, None, None)


def policy_binding(snapshot: PolicySnapshot) -> tuple[str, int, str]:
    return (snapshot.document.policy_id, snapshot.document.version, snapshot.checksum)


def same_policy_binding(binding: tuple[str, int, str], snapshot: PolicySnapshot) -> bool:
    """Una aprobación solo vale para el mismo policy_id, versión y checksum."""

    return binding == policy_binding(snapshot)


def _evaluate(
    canonical_request: EvaluationRequest | dict[str, object],
    trusted_context: TrustedContext | dict[str, object],
    policy_snapshot: PolicySnapshot | None,
    request_id: str,
) -> DecisionResult:
    if policy_snapshot is None:
        risk = _risk_for_missing(canonical_request)
        return _closed(request_id, ReasonCode.POLICY_MISSING, risk, None, None)
    if not isinstance(policy_snapshot, PolicySnapshot):
        return _closed(request_id, ReasonCode.AUTHORIZATION_UNAVAILABLE, Risk.HIGH, None, None)
    document = _document_or_none(policy_snapshot)
    if document is None:
        return _closed(request_id, ReasonCode.POLICY_INVALID, Risk.HIGH, None, None)
    if document_checksum(document) != policy_snapshot.checksum:
        return _closed(
            request_id,
            ReasonCode.DIGEST_MISMATCH,
            Risk.CRITICAL,
            document.policy_id,
            document.version,
        )
    request = _parse_request(canonical_request)
    if request is None:
        return _closed(request_id, ReasonCode.DEFAULT_DENY, Risk.HIGH, document.policy_id, document.version)
    context = _parse_context(trusted_context)
    if context is None:
        return _closed(
            request_id,
            ReasonCode.AUTHORIZATION_UNAVAILABLE,
            Risk.HIGH,
            document.policy_id,
            document.version,
        )
    if request.agent_id != context.agent_id:
        risk, _known = classify(request.tool.value, request.operation, request.resource_id, None)
        return _closed(request_id, ReasonCode.DEFAULT_DENY, risk, document.policy_id, document.version)
    try:
        parsed = parse_parameters(request.tool.value, request.operation, request.parameters)
    except ParameterRejected:
        risk, _known = classify(request.tool.value, request.operation, request.resource_id, None)
        return _closed(request_id, ReasonCode.DEFAULT_DENY, risk, document.policy_id, document.version)
    risk, known = classify(request.tool.value, request.operation, request.resource_id, context.risk)
    matched = [
        rule
        for rule in document.rules
        if rule_matches(rule, request, context, risk, parsed)
    ]
    decision, reason, ids = _decide(matched, risk, known)
    return _result(request.request_id, decision, reason, ids, document.policy_id, document.version, risk)


def _document_or_none(snapshot: PolicySnapshot) -> PolicyDocument | None:
    data = snapshot.document.model_dump(mode="json", by_alias=True, exclude_none=True)
    report = validate_mapping(data)
    if not report.valid or report.document is None:
        return None
    return report.document


def _parse_request(value: EvaluationRequest | dict[str, object]) -> EvaluationRequest | None:
    if isinstance(value, EvaluationRequest):
        return value
    try:
        return EvaluationRequest.model_validate(value)
    except ValidationError:
        return None


def _parse_context(value: TrustedContext | dict[str, object]) -> TrustedContext | None:
    if isinstance(value, TrustedContext):
        return value
    try:
        return TrustedContext.model_validate(value)
    except ValidationError:
        return None


def _risk_for_missing(canonical_request: EvaluationRequest | dict[str, object]) -> Risk:
    request = canonical_request if isinstance(canonical_request, EvaluationRequest) else _parse_request(canonical_request)
    if request is None:
        return Risk.HIGH
    try:
        parse_parameters(request.tool.value, request.operation, request.parameters)
    except ParameterRejected:
        return Risk.HIGH
    risk, _known = classify(request.tool.value, request.operation, request.resource_id, None)
    return risk


def _decide(matched: list, risk: Risk, known: bool) -> tuple[Decision, ReasonCode, list[str]]:
    ids = sorted(rule.id for rule in matched)
    effects = {rule.effect for rule in matched}
    if not known or risk is Risk.CRITICAL:
        if Decision.DENY in effects:
            return Decision.DENY, ReasonCode.RULE_DENY, ids
        return Decision.DENY, ReasonCode.DEFAULT_DENY, ids
    if Decision.DENY in effects:
        return Decision.DENY, ReasonCode.RULE_DENY, ids
    if Decision.REQUIRE_APPROVAL in effects:
        return Decision.REQUIRE_APPROVAL, ReasonCode.APPROVAL_REQUIRED, ids
    if Decision.ALLOW in effects:
        return Decision.ALLOW, ReasonCode.RULE_ALLOW, ids
    return Decision.DENY, ReasonCode.DEFAULT_DENY, ids


def _result(
    request_id: str,
    decision: Decision,
    reason: ReasonCode,
    matched_ids: list[str],
    policy_id: str | None,
    policy_version: int | None,
    risk: Risk,
) -> DecisionResult:
    if risk is Risk.CRITICAL and decision is not Decision.DENY:
        decision = Decision.DENY
        reason = ReasonCode.DEFAULT_DENY
    return DecisionResult(
        request_id=request_id,
        decision=decision,
        reason_code=reason,
        matched_rule_ids=matched_ids,
        policy_id=policy_id,
        policy_version=policy_version,
        risk=risk,
    )


def _closed(
    request_id: str,
    reason: ReasonCode,
    risk: Risk,
    policy_id: str | None,
    policy_version: int | None,
) -> DecisionResult:
    return _result(request_id, Decision.DENY, reason, [], policy_id, policy_version, risk)


def _extract_request_id(canonical_request: object) -> str:
    raw: object = None
    if isinstance(canonical_request, EvaluationRequest):
        return canonical_request.request_id
    if isinstance(canonical_request, dict):
        raw = canonical_request.get("request_id")
    if isinstance(raw, str):
        try:
            return str(UUID(raw))
        except ValueError:
            return NIL_REQUEST_ID
    return NIL_REQUEST_ID
