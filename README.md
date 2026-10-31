# WALLBA — AI Agent Permission Firewall

Paquete de planificación para que **cuatro desarrolladores humanos** construyan un MVP seguro y demostrable. Estado: **implementación en curso**. El módulo de Persona 1 está implementado y pendiente de revisión; faltan los módulos de P2, P3 y P4, por lo que aún no hay evidencia de protección de punta a punta. Puesta en marcha: [laboratorio de demostración](backend/wallba/demo/README.md).

Empezar por [informe final](docs/FINAL_REPORT.md), [plan maestro](docs/MASTER_PLAN.md) y [auditoría documental](docs/PLAN_AUDIT.md). La aprobación humana del plan precede cualquier implementación funcional.

## Manual de cada persona

| Persona | Entrega | Esfuerzo | Manual independiente |
|---|---|---:|---|
| 1 | Base, agente, herramientas, ejecutor, demo e infraestructura | 25 % | [PERSON_1_MASTER_PLAN](docs/team/PERSON_1_MASTER_PLAN.md) |
| 2 | Motor, seguridad y editor de políticas | 25 % | [PERSON_2_MASTER_PLAN](docs/team/PERSON_2_MASTER_PLAN.md) |
| 3 | Identidad, proxy y aprobaciones backend/UI | 25 % | [PERSON_3_MASTER_PLAN](docs/team/PERSON_3_MASTER_PLAN.md) |
| 4 | Diseño, auditoría, dashboard y experiencia de demostración | 25 % | [PERSON_4_MASTER_PLAN](docs/team/PERSON_4_MASTER_PLAN.md) |

Cada manual incluye 23 secciones y un prompt final para Cursor. Abrir esta carpeta como raíz del proyecto; leer [AGENTS](AGENTS.md) y [flujo Cursor](docs/CURSOR_WORKFLOW.md). No hacen falta credenciales de herramientas reales para la demo.

## Índice documental

| Documento | Función |
|---|---|
| [MASTER_PLAN](docs/MASTER_PLAN.md) | Alcance y decisiones del MVP |
| [REPOSITORY_INSPECTION](docs/REPOSITORY_INSPECTION.md) | Estado observado, acceso remoto fallido y supuestos |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Servicios, límites, diagramas y estructura de código propuesta |
| [TECH_STACK](docs/TECH_STACK.md) | Comparación, versiones objetivo y fuentes oficiales |
| [SECURITY_MODEL](docs/SECURITY_MODEL.md) | Amenazas, controles, aprobaciones y límites |
| [POLICY_EXAMPLES](docs/POLICY_EXAMPLES.md) | YAML/JSON completos y semántica |
| [PRODUCT_DESIGN](docs/PRODUCT_DESIGN.md) | Siete pantallas, tokens, estados y accesibilidad |
| [DATABASE_DESIGN](docs/DATABASE_DESIGN.md) | Entidades, constraints, transacciones y recuperación |
| [API_CONTRACTS](docs/API_CONTRACTS.md) | Tipos, endpoints, errores, identidad e idempotencia |
| [INTEGRATION_CONTRACTS](docs/INTEGRATION_CONTRACTS.md) | Puertos internos, eventos, mocks y gates |
| [OWNERSHIP_MATRIX](docs/OWNERSHIP_MATRIX.md) | Propiedad y revisión de paths/contratos |
| [TASK_MATRIX](docs/TASK_MATRIX.md) | 39 tareas, subtareas, estimación y aceptación |
| [WORKLOAD_BALANCE](docs/WORKLOAD_BALANCE.md) | 100 unidades y sensibilidad de estimación |
| [ROADMAP](docs/ROADMAP.md) | Ciclos relativos y entregas paralelas |
| [TEST_STRATEGY](docs/TEST_STRATEGY.md) | Pruebas y evidencia por responsable |
| [DEMO_SCENARIOS](docs/DEMO_SCENARIOS.md) | S01–S10 y manifest reproducible |
| [GITHUB_WORKFLOW](docs/GITHUB_WORKFLOW.md) | Ramas, PR, revisión, CI y recuperación |
| [CURSOR_WORKFLOW](docs/CURSOR_WORKFLOW.md) | Configuración y delegación real |
| [REQUIREMENTS_TRACEABILITY](docs/REQUIREMENTS_TRACEABILITY.md) | Requisitos -> tareas -> dueños -> pruebas |
| [PLAN_AUDIT](docs/PLAN_AUDIT.md) | Validación ejecutada y límites de lo comprobado |
| [FINAL_REPORT](docs/FINAL_REPORT.md) | Informe solicitado A–J y aprobación |

Configuración real: nueve archivos en `.cursor/agents/` (enlazados en el informe) y diez reglas `.mdc` en `.cursor/rules/`. [Plantilla PR](.github/pull_request_template.md) y [bug report](.github/ISSUE_TEMPLATE/bug_report.md).

## Validar este paquete

Requiere Python 3.12+ y biblioteca estándar; no instala dependencias ni ejecuta herramientas del producto.

```powershell
python scripts/build_plan_tables.py
python scripts/validate_plan.py
```

Fuentes de tareas: [P1](docs/planning/person-1-tasks.json), [P2](docs/planning/person-2-tasks.json), [P3](docs/planning/person-3-tasks.json), [P4](docs/planning/person-4-tasks.json). Modificar fuente, regenerar matriz/balance y actualizar manual correspondiente. El validador comprueba metadatos, DAG, secciones, frontmatter y enlaces; no demuestra funcionamiento de WALLBA o reconocimiento en una instalación de Cursor.

## Pendientes antes de código

Aprobar plan y propuesta visual; asignar nombres a P1–P4; declarar disponibilidad por ciclo. No se recibieron referencias visuales. El acceso a [GitHub](https://github.com/Gelomiterizzio/Wallba) se verificó al preparar esta publicación y el repositorio estaba vacío; la [inspección](docs/REPOSITORY_INSPECTION.md) conserva el historial de comprobaciones. No copiar este paquete sobre otros checkouts sin comparar archivos existentes.
