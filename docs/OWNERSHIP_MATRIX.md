# Propiedad de archivos y contratos

Cuatro responsables humanos. La propiedad es principal y exige revisión; no impide ayudar con un PR coordinado. Un subagente no adquiere propiedad. Paths de código son propuestos hasta aprobación.

| Ruta / contrato | Dueño | Revisión obligatoria |
|---|---|---|
| backend/wallba/contracts/, contracts/, frontend/src/api/generated.ts | P1 | P2/P3/P4 consumidores |
| backend/wallba/foundation/, agent/, executor/, demo/ | P1 | P3 para ejecutor; P2 para scopes |
| infra/, backend/pyproject.toml, backend/uv.lock, compose files, .env.example, .gitignore | P1 | P3 límites de confianza |
| backend/alembic/env.py y migración base | P1 | Todos los dominios con tablas |
| backend/wallba/policy/, policies/, frontend/src/features/policies/ | P2 | P3 consumo; P4 integración visual |
| backend/wallba/auth/, gateway/, approvals/, frontend/src/features/approvals/ | P3 | P2 seguridad; P4 UX |
| frontend/src/app/, components/, styles/ | P4 | P2/P3 como consumidores |
| frontend/src/api/ excepto generated.ts, frontend/src/mocks/ | P4 | P1 contrato; P3 auth |
| frontend/src/features/dashboard/, agents/, audit/, playground/, attack-matrix/ | P4 | P1 datos demo, P3 approvals |
| backend/wallba/observability/ | P4 | P3 transacciones y fallos |
| tests/foundation/, contracts/, agent/, executor/, demo/, infra/ | P1 | P2/P3 para aislamiento |
| tests/policy/, frontend tests dentro features/policies | P2 | P3 |
| tests/auth/, gateway/, approvals/, frontend tests dentro approvals | P3 | P2 |
| tests/observability/, e2e/, frontend tests compartidos | P4 | Dueño del flujo probado |
| backend/alembic/versions/* de cada dominio | Dueño de dominio P1/P2/P3/P4 | P1 orden de migración; no ownership compartido de un mismo archivo |
| .github/workflows/, PR template, bug template | P1 | Los cuatro revisan checks propios |
| frontend/package.json, package-lock.json, vite/ts config | P4 | P1 compatibilidad entorno; P2/P3 dependencias nuevas |
| docs/team/PERSON_N_MASTER_PLAN.md, docs/planning/person-N-tasks.json | PN | Dueños de dependencias |
| docs/API_CONTRACTS.md, INTEGRATION_CONTRACTS.md | P1 | Todos ante cambio |
| docs/SECURITY_MODEL.md, POLICY_EXAMPLES.md | P2 | P1/P3/P4 impacto |
| docs/PRODUCT_DESIGN.md | P4 | P2/P3 pantallas propias |
| docs/DATABASE_DESIGN.md | P1 | Dueños de tablas |
| docs/TEST_STRATEGY.md, DEMO_SCENARIOS.md | P4 estrategia / P1 runner | P2/P3 controles |
| README, AGENTS, MASTER_PLAN, ARCHITECTURE, TECH_STACK, ROADMAP, GITHUB_WORKFLOW, REPOSITORY_INSPECTION | P1 | Todos según alcance |
| TASK_MATRIX, WORKLOAD_BALANCE, REQUIREMENTS_TRACEABILITY, PLAN_AUDIT, FINAL_REPORT | P1 integrador documental | Los cuatro validan sus datos |
| .cursor/agents/pN-*.md | PN | Dueño del área y revisor de seguridad |
| .cursor/agents/wallba-verifier.md y .cursor/rules/*, docs/CURSOR_WORKFLOW.md | P1 | Los cuatro |
| scripts/validate_plan.py, scripts/build_plan_tables.py | P1 | P2 comprobación del verificador |

Todo archivo nuevo debe elegir uno de estos scopes o añadirse a esta tabla antes del PR. `AGENTS.md` no es un mecanismo técnico de sandbox. Contratos y locks no se editan simultáneamente sin coordinación. P4 hace routing de las pantallas P2/P3 mediante interfaces exportadas, sin editar lógica interna ajena.

Proceso de cambio compartido: issue/RFC -> ejemplo antes/después -> propietario propone -> consumidores prueban -> PR pequeño -> actualizar docs/mocks/generados -> merge autorizado. Bloqueos y desacuerdos se registran con ID y dueño; no se resuelven sobrescribiendo ramas.

[Tareas](TASK_MATRIX.md) · [Índice](../README.md)
