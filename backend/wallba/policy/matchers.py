"""Coincidencia conjuntiva. Un campo desconocido no se ignora: falla cerrado."""

from __future__ import annotations

from wallba.policy.models import Conditions, EvaluationRequest, Risk, Rule, TrustedContext
from wallba.policy.parameters import parameters_match
from wallba.policy.risk import risk_rank


def rule_matches(
    rule: Rule,
    request: EvaluationRequest,
    context: TrustedContext,
    risk: Risk,
    parsed: object,
) -> bool:
    if request.agent_id not in rule.agents:
        return False
    tool = request.tool.value
    if tool not in {item.value for item in rule.tools}:
        return False
    if request.resource_id not in rule.resources:
        return False
    conditions = rule.conditions
    if conditions is None:
        return True
    if not isinstance(conditions, Conditions):
        raise TypeError("conditions")
    if conditions.principal_roles is not None and not set(conditions.principal_roles).intersection(context.roles):
        return False
    if conditions.context_environments is not None and context.environment_id not in conditions.context_environments:
        return False
    if conditions.risk_at_most is not None and risk_rank(risk) > risk_rank(conditions.risk_at_most):
        return False
    if conditions.parameters is not None:
        if parsed is None:
            return False
        if not parameters_match(tool, parsed, conditions.parameters):
            return False
    return True
