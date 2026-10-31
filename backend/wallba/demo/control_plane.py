"""S09: ensayo del plano de control con el motor real. No ejecuta herramientas."""

from __future__ import annotations

from wallba.contracts.ports import HarnessObservation

# El efecto desconocido es lo que S09 debe hacer rechazar.
INVALID_POLICY = """\
schema_version: "1"
policy_id: demo-policy
version: 999
rules:
  - id: invalid-rule
    effect: MAYBE
    agents: [demo-agent]
    tools: [file.read]
    resources: ["file:public-guide"]
"""


class ControlPlaneHarness:
    """Responde S09 con una observación real y delega las demás secuencias."""

    def __init__(self, inner, policy_service) -> None:
        self._inner = inner
        self._policy = policy_service

    def observe(self, scenario_id, run_id, request_ids):
        if scenario_id != "S09":
            return self._inner.observe(scenario_id, run_id, request_ids)
        return self._observe_invalid_policy()

    def _observe_invalid_policy(self) -> HarnessObservation:
        before = self._policy.get_active_snapshot()
        if before is None:
            return HarnessObservation(state="INCOMPLETE", note="No hay política activa con la que comparar")
        report = self._policy.validate_content(INVALID_POLICY, "yaml")
        after = self._policy.get_active_snapshot()
        if report.valid:
            return HarnessObservation(state="OBSERVED", note="ALERTA: el motor aceptó una política inválida")
        if after is None or after.checksum != before.checksum:
            return HarnessObservation(state="OBSERVED", note="ALERTA: la política activa cambió durante el ensayo")
        return HarnessObservation(
            state="OBSERVED",
            note=(
                "Validación real del servicio de políticas: documento rechazado y política activa "
                "intacta. Prueba automática, sin el paso humano por la interfaz."
            ),
        )
