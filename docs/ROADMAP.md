# Roadmap relativo

No se conocen horas disponibles. Un ciclo es una ventana de trabajo con capacidad declarada por cada persona al iniciar; no equivale a una semana. Propuesta: 6 ciclos, ajustar tras medir velocidad del primer bloque. Aprobar plan y acceso al checkout antes del ciclo 0. No son cuatro fases por persona.

| Etapa | Trabajo simultáneo y dueños | Dependencias / entregables | Validación / salida / riesgo |
|---|---|---|---|
| 0 — Contratos y preparación | P1 DTO/infra mínima; P2 schema/loader; P3 state machine/auth design; P4 tokens/MSW | snapshot API, fixtures, paths y decisiones | Todos revisan ejemplos; sin cambios remotos automáticos. Riesgo: repo no accesible |
| 1 — Cortes iniciales | P1 herramientas/agent; P2 evaluator; P3 auth/gateway con FakePolicy; P4 shell/AuditSink | puertos y mocks de etapa0 | Unit/contract tests, DENY counter=0 con fake. Riesgo: divergencia de schemas |
| 2 — Integración progresiva | P1 ejecutor aislado; P2 API/editor; P3 approvals API/UI; P4 lectura audit/dashboard/agents | capacidad, AuditSink, primitivas | Flujo ALLOW/DENY real aislado y persistencia. Riesgo: credenciales/redes |
| 3 — Seguridad y comparación | P1 runner/fixtures; P2 adversariales; P3 replay/races/crash; P4 playground/matriz | ejecutor+gateway y eventos estables | S01–S10 desde seed, evidencia parcial válida. Riesgo: UNKNOWN mal interpretado |
| 4 — Diseño completo y E2E | P1 recovery/CI; P2 UI errores/diffs; P3 approval accesible; P4 responsive/axe/E2E | rutas integradas sin mocks finales | Gating CI y revisión humana; ningún crítico abierto. Riesgo: carga visual subestimada |
| 5 — Ensayo y entrega | P1 reset/runbook; P2 revisa políticas; P3 verifica aprobación exacta; P4 presenta evidencia | todos los criterios y manifest | Repetición limpia, informe real, limitaciones conocidas. Riesgo: entorno de demo distinto |

## Hitos

M0 contratos congelados para primer corte; M1 agente simulado y decisiones puras; M2 enforcement real y aprobación de consumo único; M3 comparación pareada reproducible; M4 E2E/seguridad/visual verificadas; M5 demo y documentación revisadas. P1 coordina integración dentro de sus 25 puntos, no hace pruebas ajenas.

La ruta crítica es DTO -> gateway+ejecutor -> consumo de aprobación -> runner pareado -> evidencia. El motor y UI se construyen contra mocks desde etapa0. Cada ciclo reserva integración y documentación dentro de los puntos, no añade un quinto paquete ni puntos fuera de presupuesto.

Al terminar cada ciclo registrar esfuerzo real, bloqueos e incertidumbres. Si el trabajo cambia, proponer recorte explícito o transferencia cohesionada de tareas con revisión; recalcular 25/25/25/25 manteniendo trazabilidad, sin cambiar números para ocultar tiempo real. Ver [equilibrio](WORKLOAD_BALANCE.md).

[Tareas](TASK_MATRIX.md) · [Índice](../README.md)
