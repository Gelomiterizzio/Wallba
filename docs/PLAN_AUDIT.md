# Auditoría de la planificación

Fecha: 31/10/2026. Este informe cubre documentos y metadatos, no funcionamiento del producto.

## Comprobaciones ejecutadas

Se ejecutaron `python Wallba/scripts/build_plan_tables.py` y `python Wallba/scripts/validate_plan.py` desde el workspace padre con Python 3.13.15. Ambos terminaron con exit code **0** en la verificación final. No se instalaron dependencias ni se ejecutaron suites del producto.

| Comprobación ejecutada | Resultado observado |
|---|---|
| Cuatro fuentes de tareas / responsables | 4 / P1,P2,P3,P4 |
| Presupuesto por persona | 25, 25, 25, 25 |
| Total normalizado | 100 |
| Tareas / IDs únicos | 39 / 39 |
| Dependencias existentes y sin ciclos | PASS |
| Criterios, pruebas y justificación en metadatos | Presentes en todas las tareas |
| Manuales con secciones numeradas 1–23 | 4 |
| Correspondencia IDs manual/matriz | PASS |
| Subagentes y frontmatter escalar | 9; auditores readonly |
| Reglas .mdc | 10 |
| Enlaces locales | 48 documentos revisados; 0 enlaces rotos |

La primera ejecución detectó tres campos subagent que mezclaban texto humano con el nombre del agente. Se normalizaron al identificador `wallba-verifier`, conservando al humano como responsable en owner y manual, se regeneraron tablas y se volvió a ejecutar el validador con éxito.

## Revisión de contenido

Se inspeccionaron los cuatro manuales y los contratos globales. Hallazgos corregidos: resource_version se comprueba dentro de transacción del ejecutor; campos request_id/request_digest nullable para eventos administrativos; solicitante y aprobador siempre distintos; tabla canónica de reason codes; locks frontend propiedad P4; scopes de fixture permiten alcanzar el motor; S09 requiere humano policy_admin sin conceder privilegio al runner. Se fijó punto de autorización transaccional y límite de revocación en vuelo TTL30s.

## Límites de la verificación

El validador revisa el subconjunto escalar de frontmatter utilizado, no implementa un parser general YAML ni ejecuta Cursor. Reconocimiento por Cursor, instalación de dependencias, pruebas unitarias/integración/E2E/seguridad/visual, CI y demostraciones están pendientes de implementación. Ningún escenario figura como aprobado. Inspección remota de GitHub no disponible por fallos de acceso, sin inferir contenido. Referencias visuales no entregadas; diseño propuesto rotulado.

[Trazabilidad](REQUIREMENTS_TRACEABILITY.md) · [Informe](FINAL_REPORT.md) · [Índice](../README.md)
