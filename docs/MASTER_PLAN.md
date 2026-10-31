# WALLBA — plan maestro

WALLBA es un firewall de permisos entre un agente de IA y cuatro herramientas sintéticas. Intercepta cada llamada, autentica identidad y scope, evalúa políticas deterministas YAML/JSON y permite, deniega o solicita aprobación humana. Produce auditoría y comparación reproducible con/sin protección. Estado: **planificación; requiere aprobación antes de implementar**.

## Base de evidencia y alcance

La solicitud original está descompuesta en [trazabilidad](REQUIREMENTS_TRACEABILITY.md). El workspace no tiene checkout y el remoto no se pudo consultar; no se presupone vacío. [Inspección](REPOSITORY_INSPECTION.md). No se recibieron referencias visuales; [diseño](PRODUCT_DESIGN.md) identifica una propuesta, no material del usuario.

MVP: cuatro tools (`file.read`, `email.send`, `record.delete`, `db.query`), agente guionado con tool calls, gateway obligatorio, motor puro, políticas versionadas/editables, identidad separada humano/agente, aprobación exacta con expiración/CAS, auditoría consultable, siete pantallas y diez escenarios. Simulación es funcional y reproducible; no se presenta como evaluación de un LLM general. No hay datos reales, SMTP, raw SQL, herramientas de shell, multitenancy o despliegue público.

Futuro: adaptador live a proveedor elegido, PostgreSQL/múltiples workers, OIDC/SSO, conectores reales, motor externo, auditoría inmutable externa, revocación online y alta disponibilidad. Cada incremento se estima aparte. Estas exclusiones preservan la demostración del firewall sin prometer garantías que el MVP no tiene.

## Arquitectura y decisiones

React/TypeScript/Vite consume API FastAPI tipada. SQLite de control guarda identidad, solicitudes, políticas, aprobaciones y auditoría; ejecutor separado posee solo recursos sintéticos y journal. Agente sin secretos/mounts del ejecutor. Baseline está en entorno distinto; no existe bypass sobre protected. [Arquitectura con diagramas](ARCHITECTURE.md), [stack comparado y fuentes](TECH_STACK.md), [datos](DATABASE_DESIGN.md).

Decisiones críticas: DENY por defecto; DENY > REQUIRE_APPROVAL > ALLOW; scopes de credencial acotan políticas; validación estricta; no autoridad en texto del modelo; snapshot y digest exactos; aprobación humana no reutilizable; claim duradero; capacidad HMAC corta; UNKNOWN ante ambigüedad; auditoría saneada. [Modelo de seguridad](SECURITY_MODEL.md).

## Cuatro entregas equilibradas

| Persona | Entrega coherente | Unidades | Porcentaje |
|---|---|---:|---:|
| P1 | Contratos/base, agente, ejecutor, fixtures, runner e infraestructura | 25 | 25 % |
| P2 | Motor/seguridad de políticas, repositorio/API y editor visual | 25 | 25 % |
| P3 | Identidad, gateway, aprobaciones exactas y centro visual | 25 | 25 % |
| P4 | Diseño/shell, auditoría, dashboard, Playground, matriz y E2E coordinado | 25 | 25 % |
| **Total** | **Cuatro humanos** | **100** | **100 %** |

Los puntos no garantizan tiempo idéntico. [Balance y sensibilidad](WORKLOAD_BALANCE.md), [matriz completa](TASK_MATRIX.md) y [propiedad](OWNERSHIP_MATRIX.md) fijan distribución. La UI de políticas/aprobaciones se movió a P2/P3 y el backend del runner a P1 para reducir concentración de P4. Integración, pruebas y docs están en las cuatro cargas.

## Desarrollo paralelo y contratos

En etapa0 se acuerdan DTO, fixtures, puertos y API; luego cada persona usa mocks definidos por el mismo esquema. No se espera a que P1 termine toda la base. [API_CONTRACTS](API_CONTRACTS.md) define HTTP, tipos y errores; [INTEGRATION_CONTRACTS](INTEGRATION_CONTRACTS.md) define interfaces, transacciones, eventos y capacidades. Cambios incompatibles requieren revisión de consumidores y actualización conjunta de ejemplos/generados/tests.

## Manuales ejecutables

- [Persona 1](team/PERSON_1_MASTER_PLAN.md): base, herramientas y entorno.
- [Persona 2](team/PERSON_2_MASTER_PLAN.md): políticas y seguridad.
- [Persona 3](team/PERSON_3_MASTER_PLAN.md): proxy e intervención humana.
- [Persona 4](team/PERSON_4_MASTER_PLAN.md): experiencia y evidencia.

Cada manual contiene 23 secciones, tareas con criterios, paths, pruebas, delegación, límites, entrega y prompt final. [Cursor](CURSOR_WORKFLOW.md) define los nueve subagentes y reglas reales. Son asistentes, no dueños humanos adicionales.

## Gates y aceptación global

Contrato revisado -> decisiones unitarias -> enforcement aislado -> aprobación single-use -> paired demo -> validación de seguridad/UI -> demo final. [Roadmap](ROADMAP.md) no asume horas disponibles. [Pruebas](TEST_STRATEGY.md) asigna responsabilidad propia y evidencia; [Demo](DEMO_SCENARIOS.md) define S01–S10, sin resultados inventados.

Terminado cuando una instalación limpia reproduce agente/tool calls, deny sin despacho, allow con receipt, aprobación humana exacta y única, siete pantallas accesibles, matriz basada en evidencia y recuperación ante errores. Ningún check de producto se ha ejecutado durante esta fase. No usar un documento de planificación como prueba de protección real.

## Riesgos y decisiones pendientes

Acceso al repo y adaptación al estado real; habilidad/disponibilidad de cuatro humanos; compatibilidad exacta de dependencias al bloquear versiones; parser y carreras; límite de revocación en vuelo; auditoría local modificable por root; expectativas sobre agente guionado; aprobación del diseño sin referencias. Mitigaciones en manuales/modelo de seguridad, sin ocultar incertidumbre. Obtener aprobación del plan antes de código, y autorización separada para publicar remotamente.

[Informe final](FINAL_REPORT.md) · [Auditoría documental](PLAN_AUDIT.md) · [Índice](../README.md)
