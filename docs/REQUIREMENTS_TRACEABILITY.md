# Trazabilidad de requisitos

Los IDs R01–R30 siguen las secciones de la solicitud; subdivisiones cubren controles o pantallas específicos. Las referencias a pruebas son **planificadas**, salvo validación documental registrada en PLAN_AUDIT. Cada fila enlaza tareas, dueños y aceptación; las subtareas y comandos están en TASK_MATRIX y manuales.

| Requisito | Cobertura | Tareas | Responsable | Especificación | Prueba / criterio |
|---|---|---|---|---|---|
| R01 | Inspeccionar estado local/remoto e idioma | WAL-P1-001 | P1 | [Documento](REPOSITORY_INSPECTION.md) | Inspección antes de scaffold; remoto desconocido no se considera vacío |
| R02 | Cuatro tools y agente demostrable | WAL-P1-004, WAL-P1-005 | P1 | [Documento](team/PERSON_1_MASTER_PLAN.md) | Cuatro receipts tipados y transcript determinista, solo datos sintéticos |
| R03 | Referencias visuales y ausencia de material adicional | WAL-P4-001 | P4 | [Documento](PRODUCT_DESIGN.md) | Propuesta rotulada; no inventar referencias |
| R04 | 100 unidades y exactamente cuatro humanos | WAL-P1-001 | P1–P4 | [Documento](WORKLOAD_BALANCE.md) | validate_plan.py comprueba cuatro owners, 25 cada uno y total100 |
| R05 | Reequilibrar módulos sin quinta parte | WAL-P2-007, WAL-P3-007, WAL-P4-009 | P2/P3/P4 | [Documento](OWNERSHIP_MATRIX.md) | Políticas y approvals UI en sus dueños; pruebas repartidas |
| R06 | Cuatro manuales independientes y 23 secciones | WAL-P1-001 | P1–P4 | [Documento](MASTER_PLAN.md) | Validador cuenta cuatro manuales y secciones 1..23 |
| R07 | Manual: objetivos, arquitectura, paths y contratos | WAL-P1-001 | P1–P4 | [Documento](API_CONTRACTS.md) | Cada tarea aparece en su manual y matriz; revisión humana de contenido |
| R08 | Nueve subagentes Cursor reales | WAL-P1-001 | P1–P4 | [Documento](CURSOR_WORKFLOW.md) | Nueve archivos, campos compatibles y readonly auditores; reconocimiento UI pendiente |
| R09 | Contexto, límites y reporte de cada subagente | WAL-P1-001 | P1–P4 | [Documento](CURSOR_WORKFLOW.md) | Informe con ID, archivos, decisiones, comandos, resultado y riesgos |
| R10 | Orquestación, worktrees y control humano | WAL-P1-010, WAL-P2-010, WAL-P3-010, WAL-P4-009 | P1–P4 | [Documento](CURSOR_WORKFLOW.md) | No colisión de escritores ni éxito sin evidencia |
| R11 | Matriz de todas las tareas y script | WAL-P1-001 | P1 | [Documento](TASK_MATRIX.md) | 39 IDs únicos, DAG, aceptación, owner y justificación |
| R12 | Proxy obligatorio y diagramas | WAL-P3-003, WAL-P1-006 | P3/P1 | [Documento](ARCHITECTURE.md) | DENY no despacha; acceso directo sin capacidad falla |
| R13 | Investigar y comparar stack | WAL-P1-002, WAL-P4-001 | P1/P4 | [Documento](TECH_STACK.md) | Fuentes oficiales y alternativas; locks se prueban en implementación |
| R14a | Prompt injection y separación de detección/permisos | WAL-P2-008, WAL-P1-007 | P2/P1 | [Documento](SECURITY_MODEL.md) | S08 induce llamada pero política impide efecto; no prometer detección universal |
| R14b | Parámetros, archivos y query scope | WAL-P2-004, WAL-P1-004, WAL-P3-002 | P2/P1/P3 | [Documento](SECURITY_MODEL.md) | IDs virtuales y esquemas cerrados; raw SQL/path fallan |
| R14c | Escalada, exfiltración, bypass | WAL-P3-001, WAL-P1-009, WAL-P2-008 | P3/P1/P2 | [Documento](SECURITY_MODEL.md) | Agente sin rol humano ni credenciales executor; outbox sin SMTP |
| R14d | Replay, expiración, carreras, fallos y auditoría | WAL-P3-005, WAL-P3-008, WAL-P4-003 | P3/P4 | [Documento](TEST_STRATEGY.md) | CAS/nonces y UNKNOWN; fallo de intención bloquea |
| R15 | Políticas YAML/JSON, precedencia y activación | WAL-P2-001, WAL-P2-002, WAL-P2-003, WAL-P2-005 | P2 | [Documento](POLICY_EXAMPLES.md) | Mismo documento normalizado; DENY domina; versión inválida no activa |
| R16 | Aprobación humana completa y exacta | WAL-P3-004, WAL-P3-005, WAL-P3-007 | P3 | [Documento](SECURITY_MODEL.md) | S06/S07/S10 y test TTL; approver distinto siempre |
| R17a | Dashboard y agentes | WAL-P4-005, WAL-P1-005 | P4/P1 | [Documento](PRODUCT_DESIGN.md) | Datos API, KPI con as_of; scopes reales del catálogo |
| R17b | Políticas y aprobaciones visuales | WAL-P2-007, WAL-P3-007 | P2/P3 | [Documento](PRODUCT_DESIGN.md) | Edición/validación/activación; detalle y confirmación aprobaciones |
| R17c | Auditoría, Playground y matriz | WAL-P4-006, WAL-P4-007, WAL-P4-008 | P4 | [Documento](PRODUCT_DESIGN.md) | Filtros/timeline y resultados observados con enlaces a evidencia |
| R17d | Responsive, tokens, a11y y todos los estados | WAL-P4-001, WAL-P4-009 | P4 y dueños UI | [Documento](PRODUCT_DESIGN.md) | Teclado, contraste, axe y screenshots con viewport |
| R18 | Diez escenarios pareados reproducibles | WAL-P1-007, WAL-P1-008, WAL-P2-009, WAL-P3-009 | P1/P2/P3 | [Documento](DEMO_SCENARIOS.md) | Seed/digest inicial equivalente; S09 admin; no resultados inventados |
| R19 | Contratos, mocks, ownership y paralelo | WAL-P1-001, WAL-P4-002 | P1/P4 | [Documento](INTEGRATION_CONTRACTS.md) | Fixtures compartidos y puertos; gates cross-module definidos |
| R20 | GitHub, main, ramas, PR, CI y recuperación | WAL-P1-009, WAL-P1-010 | P1 y cada dueño | [Documento](GITHUB_WORKFLOW.md) | Plantillas reales; sin push/merge durante planificación |
| R21 | Reglas .mdc y AGENTS raíz | WAL-P1-001 | P1 | [Documento](CURSOR_WORKFLOW.md) | Diez reglas scoped, campos válidos y autoridad de ownership |
| R22 | Cronograma relativo y cuatro módulos simultáneos | WAL-P1-010 | P1–P4 | [Documento](ROADMAP.md) | Seis ciclos con entregables/gates sin asumir horas |
| R23 | Pruebas completas por componente | WAL-P1-010, WAL-P2-010, WAL-P3-009, WAL-P4-009 | P1–P4 | [Documento](TEST_STRATEGY.md) | Comandos, evidence y no PASS sin ejecución |
| R24 | Documentación global, links e índice | WAL-P1-001 | P1–P4 | [Documento](MASTER_PLAN.md) | Todos los archivos obligatorios presentes y enlaces locales válidos |
| R25 | Guías específicas, datos/errores/evidencia | WAL-P1-001 | P1–P4 | [Documento](TASK_MATRIX.md) | Revisión manual de tareas, no placeholders de implementación |
| R26 | Protocolo repetible con bloqueos y cambios | WAL-P1-010, WAL-P2-010, WAL-P3-010, WAL-P4-009 | P1–P4 | [Documento](CURSOR_WORKFLOW.md) | ID -> límites -> delegación -> pruebas -> revisión -> PR |
| R27 | Auditoría, cobertura y equilibrio verificable | WAL-P1-001 | P1 integrador; revisión todos | [Documento](PLAN_AUDIT.md) | Validador con exit code y corrección de hallazgos |
| R28 | Informe A–J e inicio por persona | WAL-P1-001 | P1 | [Documento](FINAL_REPORT.md) | Informe enlazado y prompts listos en cuatro manuales |
| R29 | Restricciones absolutas: no app ni remoto | WAL-P1-001 | P1–P4 | [Documento](REPOSITORY_INSPECTION.md) | Solo documentación/config de asistentes/scripts de metadatos |
| R30 | Orden y gate aprobación de implementación | WAL-P1-001 | P1 | [Documento](FINAL_REPORT.md) | Plan revisable completo, solicitud final antes de código |

Las veinte reglas absolutas se cubren mediante R04/R06/R08/R11/R14/R19/R23/R29/R30: cuatro humanos, 25 puntos, manuales reales, subagentes reales, dueños únicos, contratos, diseño rotulado, seguridad prioritaria, evidencia honesta, datos sintéticos, pruebas dentro de cargas, MVP separado de futuro, archivos escritos, sin remoto y aprobación antes de implementar.

[Índice](../README.md)

