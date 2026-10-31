# Progreso de Persona 2

Registro de ejecución. No sustituye a `docs/MASTER_PLAN.md` ni a `docs/team/PERSON_2_MASTER_PLAN.md`.

## 1. Resumen del proyecto

WALLBA es un firewall de permisos entre un agente de IA y cuatro herramientas sintéticas (`file.read`, `email.send`, `record.delete`, `db.query`). El agente propone una llamada; el servidor autentica, evalúa una política versionada y responde `ALLOW`, `DENY` o `REQUIRE_APPROVAL`. Si no hay una regla que conceda el efecto, la decisión es `DENY`. Una aprobación humana no convierte en permitida una operación prohibida.

El plan original está en `docs/MASTER_PLAN.md`. El manual de esta persona es `docs/team/PERSON_2_MASTER_PLAN.md`. Los contratos que mandan sobre los tipos compartidos son `docs/API_CONTRACTS.md` y `docs/INTEGRATION_CONTRACTS.md`.

Stack previsto: Python 3.12, Pydantic 2, FastAPI, SQLite, PyYAML, React 19 y TypeScript. Persona 1 aún no ha publicado `backend/pyproject.toml` ni Alembic. Persona 4 aún no ha publicado el proyecto Vite.

## 2. Responsabilidades de Persona 2

Módulo Policy and Security, 25 puntos, tareas `WAL-P2-001` a `WAL-P2-010` en `docs/planning/person-2-tasks.json`.

Rutas propias: `backend/wallba/policy/`, `policies/`, `tests/policy/` y `frontend/src/features/policies/`.

Quedan fuera: agente, ejecutor, catálogo de infraestructura y migraciones base (P1); identidad, CSRF real, gateway y aprobaciones (P3); shell, tokens compartidos y pantallas de auditoría (P4).

## 3. Plan de trabajo por fases

El orden sale de `docs/ROADMAP.md` y de las dependencias de cada `WAL-P2`.

| Etapa | Tareas | Entregable |
|---|---|---|
| 0 | WAL-P2-001, WAL-P2-002 | Esquema estricto y cargador acotado |
| 1 | WAL-P2-003, WAL-P2-004 | Evaluador determinista, parámetros y riesgo |
| 2 | WAL-P2-005, WAL-P2-006, WAL-P2-007 | Versiones inmutables, API y editor |
| 3 | WAL-P2-008, WAL-P2-009 | Corpus adversarial y política de laboratorio |
| Integración | WAL-P2-010 | El proxy de P3 debe reevaluar con el snapshot vigente |

## 4. Progreso de implementación

| Tarea | Estado | Evidencia |
|---|---|---|
| WAL-P2-001 Esquemas | Completada | `tests/policy/test_schema.py` pasó. Un campo desconocido se rechaza con ruta y no muta el documento ya validado. |
| WAL-P2-002 Cargador | Completada | `tests/policy/test_loader.py` pasó. Alias, tag, clave duplicada, profundidad, tamaño y float se rechazan. YAML y JSON equivalentes comparten checksum. |
| WAL-P2-003 Evaluador | Completada | `tests/policy/test_evaluator.py` pasó. `DENY` gana en las 6 permutaciones y los IDs coincidentes salen ordenados. |
| WAL-P2-004 Parámetros y riesgo | Completada | `tests/policy/test_parameters.py` pasó. Destinatario fuera de la lista y `query_id` desconocido terminan en `DENY`. El riesgo declarado no rebaja `record.delete`. |
| WAL-P2-005 Repositorio | Completada en el puerto, con adaptador provisional | `tests/policy/test_activation.py` pasó, incluida la activación concurrente: un éxito y un conflicto. Guardar no activa. Un fallo de auditoría revierte el puntero. Al reabrir el archivo siguen el histórico y la versión activa. |
| WAL-P2-006 API | Completada contra el doble de identidad | `tests/policy/test_api.py` pasó. Agente y viewer reciben 403 y el snapshot no cambia. Validar un documento inválido responde 422 y no inserta versiones. |
| WAL-P2-007 Editor | Implementada, pendiente de validación visual | La máquina de estados pasó en Node. Las páginas React existen y no se ejecutaron en navegador: no hay proyecto Vite. |
| WAL-P2-008 Adversarial | Completada en el motor | `tests/policy/test_adversarial.py` pasó. No hay código de proxy que auditar todavía. |
| WAL-P2-009 Catálogo demo | Completada en el motor | `tests/policy/test_demo_policy.py` pasó. YAML y JSON producen las mismas decisiones de S01–S06 y S08. |
| WAL-P2-010 Integración | Parcial, bloqueada en P3 y en el DOM | `tests/policy/test_contract_integration.py` y `activation.test.ts` pasaron. El gateway real no existe, así que no hay prueba de que una aprobación de P3 quede inutilizada dentro del proxy. |

Decisiones que no cambian el contrato de decisión:

- El checksum es SHA-256 hexadecimal del JSON canónico: UTF-8, claves ordenadas, sin espacios, cadenas NFC, sin floats.
- La precedencia es `DENY`, luego `REQUIRE_APPROVAL`, luego `ALLOW`. Sin coincidencia, `DEFAULT_DENY`.
- `CRITICAL` no puede terminar en `ALLOW` ni en `REQUIRE_APPROVAL`.
- El riesgo de catálogo no se rebaja. `record.delete` y `email.send` son `HIGH`; la lectura pública y `db.query` son `LOW`; la lectura restringida es `HIGH`.
- `policies/demo.yaml` añade `allow-demo-query` al ejemplo de tres reglas de `docs/POLICY_EXAMPLES.md`, porque S03 exige un `ALLOW` explícito. Los dos archivos de laboratorio siguen siendo equivalentes entre sí.
- La persistencia usa `sqlite3` de la biblioteca estándar y las tablas `policy_versions` y `policy_activation` descritas en `docs/DATABASE_DESIGN.md`. Falta la migración Alembic de P1.
- Los códigos HTTP `UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND` y `CONFLICT` no están nombrados en la tabla de reason codes. El conflicto de activación sí usa `STALE_POLICY`. Hace falta acuerdo con P1 antes de fijarlos en OpenAPI.

## 5. Archivos modificados

No había código de aplicación en `4b6f9e6`. Todo lo siguiente es nuevo, en la rama local `feature/person-2-policies`, sin commit.

| Ruta | Cambio |
|---|---|
| `backend/wallba/policy/` | Modelos, cargador, evaluador, parámetros, riesgo, repositorio, servicio, rutas y `schema.sql` |
| `policies/demo.yaml`, `policies/demo.json` | Política de laboratorio equivalente |
| `policies/invalid/duplicate-key.yaml` | Fixture no activable |
| `policies/examples/README.md` | Límites y expectativas del motor |
| `tests/policy/` | Pruebas de esquema, carga, evaluación, parámetros, activación, API, adversarial, demo e integración |
| `frontend/src/features/policies/` | Lista, editor, cliente HTTP, estado del borrador y pruebas de ese estado |
| `PROGRESO_PERSONA_2.md` | Este registro |
| `DEPENDENCIAS_PERSONA_2.md` | Qué falta de P1, P3 y P4, y por qué |

No se editaron módulos de P1, P3 ni P4, ni los contratos canónicos.

## 6. Pruebas realizadas

Entorno: Python 3.12.10, Windows 11, pydantic 2.14.2, PyYAML 6.0.3, pytest 9.2.0, FastAPI 0.162.0, Node 24.15.0. Commit base `4b6f9e6`. Las dependencias se instalaron fuera del repositorio, en un directorio temporal, porque `backend/pyproject.toml` pertenece a P1 y no existe.

```text
py -3 -m pytest tests/policy -q --tb=line
40 passed, 1 warning in 1.47s
```

La advertencia es de Starlette: el `TestClient` de FastAPI 0.162 pide `httpx2`. No cambia los resultados.

```text
node --experimental-strip-types --test frontend/src/features/policies/__tests__/editor.test.ts frontend/src/features/policies/__tests__/activation.test.ts
8 passed
```

No se ejecutó `npm --prefix frontend run test` porque no existe `frontend/package.json`. No se abrió el editor en un navegador. No se ejecutó el runner pareado S01–S10: no hay ejecutor ni gateway. Las decisiones de la tabla de `policies/examples/README.md` son resultados del motor, no receipts del demo.

## 7. Dependencias con otros integrantes

Persona 1:

- Publicar el entorno Python y el lock.
- Añadir la migración Alembic de `policy_versions` y `policy_activation` con el SQL ya usado por el repositorio.
- Confirmar si el catálogo sintético crece; los identificadores desconocidos se rechazan al validar y se deniegan al evaluar.

Persona 3:

- Rellenar `PolicyActor` desde la sesión real. El motor no lee cookies.
- Llamar `evaluate(canonical_request, trusted_context, policy_snapshot)` con el snapshot leído en la misma unidad de trabajo que el claim.
- No reutilizar una aprobación si `policy_binding` cambia. La función `same_policy_binding` compara política, versión y checksum.
- Comprobar el scope de la credencial antes de evaluar. Una regla `ALLOW` no amplía el scope.
- Tratar `AUTHORIZATION_UNAVAILABLE`, `POLICY_MISSING`, `POLICY_INVALID` y `DIGEST_MISMATCH` como bloqueo, nunca como permiso.

Persona 4:

- Montar `PolicyListPage` y `PolicyEditorPage` en el shell, sin editar su lógica.
- Añadir Vitest y Testing Library para las pruebas de interacción del editor.
- Los estilos de `policies.css` usan la paleta propuesta en `docs/PRODUCT_DESIGN.md` solo dentro de `.policy-feature`.

El detalle de lo que falta a las otras personas, y por qué Persona 2 no puede cerrarlo, está en [DEPENDENCIAS_PERSONA_2.md](DEPENDENCIAS_PERSONA_2.md).

## 8. Próximos pasos

1. P1 publica el proyecto Python y la migración. Entonces se sustituye el adaptador `sqlite3` por la sesión SQLAlchemy sin cambiar `PolicyService`.
2. P3 conecta el evaluador y el actor real. La prueba de aprobación obsoleta debe vivir en el gateway, usando el binding que ya devuelve este módulo.
3. P4 crea el frontend. Después se ejecutan las pruebas de teclado, foco y estados 401/403/409/422/503 sobre el DOM.
4. No hay commit ni push. El siguiente movimiento de Git queda a la espera de una autorización explícita.
