# Dependencias de Persona 2 con el resto del equipo

Persona 2 terminó, dentro de su propiedad, el motor de políticas, la publicación de versiones, la API administrativa y el editor. Este documento dice qué falta de Persona 1, Persona 3 y Persona 4, por qué no lo puede hacer Persona 2, y cómo comprobar que el encaje es correcto.

No es una ampliación del alcance. La propiedad está en `docs/OWNERSHIP_MATRIX.md`. El contrato de decisión está en `docs/API_CONTRACTS.md` y `docs/INTEGRATION_CONTRACTS.md`. El estado de lo ya construido está en `PROGRESO_PERSONA_2.md`.

## Qué ya está cerrado y no hay que rehacer

| Pieza | Dónde está | Qué garantiza |
|---|---|---|
| Esquema estricto | `backend/wallba/policy/models.py`, `schemas.py` | Un campo desconocido se rechaza con ruta. No hay coerción de `"1"` a `1` ni de `true` a entero. |
| Cargador | `backend/wallba/policy/loader.py` | YAML y JSON equivalentes dan el mismo documento. Alias, tags, claves duplicadas, profundidad, 64 KiB y cadenas de más de 2048 caracteres se rechazan. |
| Evaluador | `backend/wallba/policy/evaluator.py` | `evaluate(solicitud, contexto_confiable, snapshot) -> DecisionResult`. Precedencia `DENY` > `REQUIRE_APPROVAL` > `ALLOW`. Sin coincidencia, `DEFAULT_DENY`. |
| Parámetros y riesgo | `parameters.py`, `risk.py` | El catálogo del servidor clasifica el riesgo. El agente no puede rebajarlo. `CRITICAL` nunca queda autorizado. |
| Versiones | `repository.py`, `schema.sql` | Una versión guardada no se modifica. Activar usa compare-and-swap. Si la auditoría falla, el puntero no cambia. |
| API | `routes.py` | `GET/POST /api/v1/policies...`. Validar no activa. Agente y viewer reciben 403. |
| Editor | `frontend/src/features/policies/` | El borrador, la versión guardada y la activa son estados distintos. Un 422 conserva el texto. Un 409 no reintenta solo. |
| Política de laboratorio | `policies/demo.yaml`, `policies/demo.json` | Mismas decisiones para S01–S06 y S08. Incluye `allow-demo-query` porque S03 exige un `ALLOW` explícito. |

Pruebas ejecutadas en esta máquina, commit base `4b6f9e6`, Python 3.12.10:

- `py -3 -m pytest tests/policy -q --tb=line` — 40 passed.
- `node --experimental-strip-types --test frontend/src/features/policies/__tests__/editor.test.ts frontend/src/features/policies/__tests__/activation.test.ts` — 8 passed.

Esas pruebas no sustituyen el runner pareado, el gateway ni el navegador. Por eso las filas siguientes siguen abiertas.

## Persona 1 — base del proyecto y catálogo

Persona 1 es dueña de `backend/pyproject.toml`, el lock, Alembic, el agente, el ejecutor y los recursos sintéticos. Persona 2 no puede crear esos archivos sin invadir esa propiedad.

### 1. Entorno Python instalable

Qué hace falta: un `backend/pyproject.toml` y el lock, con Python 3.12, Pydantic 2, PyYAML 6, FastAPI y pytest. Las versiones usadas para las pruebas de Persona 2 fueron pydantic 2.14.2, PyYAML 6.0.3, pytest 9.2.0 y FastAPI 0.162.0. No son un lock del equipo: se instalaron fuera del repositorio para poder ejecutar.

Por qué: sin el proyecto de P1 no hay un comando único `uv run pytest` ni una instalación reproducible para las otras personas. Persona 2 no fija el lock porque el manual dice que P1 elige los parches.

Cómo comprobarlo: desde un clon limpio, instalar con el lock de P1 y volver a ejecutar `pytest tests/policy`. Tienen que seguir pasando las 40 pruebas sin instalar paquetes a mano.

Qué se rompe si falta: cada persona instala versiones distintas y el motor puede aceptar una coerción que otra versión de Pydantic rechaza.

### 2. Migración Alembic de las dos tablas

Qué hace falta: una revisión Alembic, hija de la migración base de P1, que cree `policy_versions` y `policy_activation`. El SQL ya está en `backend/wallba/policy/schema.sql`. Hay que ejecutarlo con `PRAGMA foreign_keys = ON`.

Por qué: `docs/DATABASE_DESIGN.md` asigna esas tablas a P2, pero `backend/alembic/env.py` y el orden de las migraciones son de P1. Crear Alembic desde cero sería una segunda historia de migraciones.

Cómo comprobarlo: base vacía, `upgrade`, guardar la versión 1, activarla, cerrar el proceso, volver a abrir y ver la misma versión activa y el mismo checksum. Repetir dos activaciones con el mismo `expected_active_version`: una gana y la otra responde 409. `tests/policy/test_activation.py` ya cubre ese comportamiento con el adaptador actual.

Qué se rompe si falta: el adaptador de `sqlite3` que usa Persona 2 crea las tablas por su cuenta. Cuando P1 entregue SQLAlchemy, hay que sustituir solo `SqlitePolicyRepository`, sin cambiar `PolicyService` ni la forma de `DecisionResult`. Si las dos vías crean el esquema, pueden divergir.

### 3. Catálogo sintético estable

Qué hace falta: que los identificadores que el ejecutor reconoce sean exactamente estos, o un cambio de contrato si crecen.

| Tipo | Identificadores |
|---|---|
| Agentes | `demo-agent`, `scoped-reader` |
| Recursos | `file:public-guide`, `file:restricted-ledger`, `mailbox:demo-outbox`, `table:demo-records`, `query:demo-records` |
| Consultas | `list_records`, `count_records` |
| Entorno protegido | `protected-fixture` |
| Roles | `viewer`, `operator`, `approver`, `policy_admin`, `agent` |

Por qué: el motor rechaza al validar un identificador que no está en el catálogo y, al evaluar, deniega un recurso que ya no está. Persona 2 no inventa archivos, filas ni buzones: eso es el ejecutor de P1.

Cómo comprobarlo: S01 lee `file:public-guide` y el digest del contenido coincide con el del baseline. S02 no abre `file:restricted-ledger`. S04 no borra la fila. S05 no añade mensajes al outbox.

Qué se rompe si falta: una regla `ALLOW` puede ser correcta y, aun así, el ejecutor no encuentra el recurso, o al revés: el ejecutor acepta un id que el motor ya no considera del catálogo.

### 4. Montar el router, no reimplementarlo

Qué hace falta: la aplicación FastAPI de P1 debe llamar `mount_policy_api(app, service, actor_provider)`. El `actor_provider` lo escribe Persona 3. El prefijo `/api/v1` ya lo añade `mount_policy_api`.

Por qué: la fábrica de la aplicación y el ciclo de vida del proceso son de P1. Duplicar las rutas en otro módulo crearía dos evaluadores.

## Persona 3 — identidad, gateway y aprobaciones

Persona 3 es dueña de `backend/wallba/auth/`, `gateway/` y `approvals/`. El motor no lee cookies, no comprueba el CSRF real y no guarda aprobaciones. Hacerlo aquí sería un segundo control de acceso, fácil de desalinear.

### 1. Traducir la sesión a `PolicyActor`

Qué hace falta: una función que el gateway llame en cada request administrativo y que devuelva `None` o un `PolicyActor`.

```python
PolicyActor(
    principal_id="demo-policy-admin",
    kind="human",          # o "agent"
    roles=frozenset({"policy_admin", "viewer"}),
    csrf_valid=True,       # solo True si el CSRF y el Origin ya se comprobaron
)
```

Reglas que la API ya aplica y que P3 no debe repetir dentro del motor:

- Sin actor: 401 `UNAUTHENTICATED`.
- `kind` distinto de `human`, o sin `policy_admin`, o con `csrf_valid` falso: 403 en validar, crear y activar.
- Leer exige `kind == "human"` y el rol `viewer`.
- Un bearer de agente sigue en 403 aunque el cuerpo diga que tiene rol `policy_admin`.

Por qué: la sesión, el hash de la cookie, el CSRF y el Origin son de P3. Persona 2 solo recibe el resultado ya decidido. Si P2 parseara la cookie, habría dos implementaciones de sesión.

Cómo comprobarlo: repetir `tests/policy/test_api.py` con el `actor_provider` real. Un agente que intenta `POST /api/v1/policies/demo-policy/activate` recibe 403 y el checksum activo no cambia. Un `policy_admin` sin CSRF recibe 403. Validar un YAML inválido recibe 422 y no inserta filas.

Qué se rompe si falta: la API queda abierta o, si alguien rellena el actor con datos del JSON del cliente, el agente se nombra administrador.

### 2. Llamar al evaluador con contexto de servidor

Qué hace falta: en el gateway, antes de cualquier efecto,

```python
decision = evaluate(canonical_request, trusted_context, snapshot)
```

`trusted_context` debe traer `principal_id`, `agent_id`, `roles`, `environment_id`, `server_time` con zona horaria, `resource_version` y, si se envía, un `risk` calculado por el servidor. El texto del prompt no entra en esa llamada. El `agent_id` de la solicitud tiene que coincidir con el del contexto; si no, el motor deniega.

`snapshot` es el que devuelve `repository.get_active_snapshot()` dentro de la misma transacción en la que se reclama la ejecución. No se busca otra política a mitad del cálculo.

Por qué: `docs/INTEGRATION_CONTRACTS.md` fija esa firma. El evaluador es puro: no abre la base ni mira el reloj. Quien tiene la transacción de control es el gateway.

Cómo comprobarlo: S08, un documento que pide borrar, produce `record.delete` y la decisión es `DENY` por `deny-delete`, con el contador del ejecutor en cero. Bajar el riesgo en el cuerpo de la petición no convierte `record.delete` en `ALLOW`.

Qué se rompe si falta: el gateway puede autorizar con una copia propia de las reglas, o fiarse del riesgo que manda el agente.

### 3. No reutilizar una aprobación de otro snapshot

Qué hace falta: al consumir una aprobación, comparar

```python
same_policy_binding((policy_id, version, checksum), snapshot_actual)
```

Si es falso, la aprobación queda inválida con `STALE_POLICY` y se vuelve a evaluar. Una aprobación de la versión 1 no ejecuta la versión 2 aunque la llamada sea la misma. `policy_binding(snapshot)` devuelve esa terna.

Por qué: Persona 2 conserva el snapshot y el checksum. Quien guarda la aprobación y decide si todavía sirve es P3. El motor no tiene tabla de aprobaciones y no debe tenerla.

Cómo comprobarlo: aprobar un `email.send` a `reviewer@example.test` con la versión 1; activar una versión 2 que deniega ese envío; intentar ejecutar. La respuesta no usa la aprobación vieja. `tests/policy/test_contract_integration.py` demuestra la diferencia de binding. Falta la prueba dentro del gateway, porque el gateway no existe.

Qué se rompe si falta: una persona aprueba un texto y, después de cambiar la política, ese permiso ejecuta otra versión.

### 4. Scope antes de evaluar, y bloquear también los fallos

Qué hace falta: si la credencial no incluye la herramienta o el recurso, responder `SCOPE_DENIED` sin llamar al ejecutor. Una regla `ALLOW` no amplía el scope. `scoped-reader` existe para ese caso.

Si el evaluador devuelve `POLICY_MISSING`, `POLICY_INVALID`, `AUTHORIZATION_UNAVAILABLE` o `DIGEST_MISMATCH`, no hay ejecución. Esos códigos no son un permiso disfrazado.

Por qué: el scope es una propiedad de la credencial, y la credencial la emite P3. El checksum lo calcula P2; comprobar que el snapshot leído no fue alterado antes del efecto también ocurre en la transacción de P3.

Cómo comprobarlo: `scoped-reader` con una regla `ALLOW` de `record.delete` sigue sin borrar. Apagar el repositorio a mitad de una activación no deja una política a medias: el test de auditoría fallida ya lo cubre en el módulo de políticas.

### 5. Auditoría en la misma transacción

Qué hace falta: un `AuditSink.append(event, connection)` que escriba en la transacción SQLite que recibe. Si lanza, la activación hace rollback. El evento que Persona 2 emite al activar solo tiene `event_type`, `policy_id`, `policy_version`, `checksum`, `actor_id` y `occurred_at`. No lleva el documento ni el cuerpo de un correo.

Por qué: la tabla `audit_events` y el encadenamiento de hashes son de P4, pero quien llama al sink dentro de la transacción de activación es el repositorio de P2, y quien define el sink de producción es el acuerdo P3/P4. Persona 2 no crea la tabla de auditoría de P4.

Cómo comprobarlo: activar con un sink que falla y comprobar que la versión anterior sigue activa. El test `test_failed_audit_rolls_back_activation` ya lo hace con un doble. El sink real tiene que usar la conexión recibida, no una conexión nueva.

## Persona 4 — shell, pruebas de navegador y auditoría visible

Persona 4 es dueña de `frontend/package.json`, `frontend/src/app/`, los componentes comunes y `frontend/src/styles/`. Persona 2 no crea el proyecto Vite porque el lock y el shell no son suyos.

### 1. Proyecto de frontend

Qué hace falta: React 19, TypeScript, Vite, Vitest y Testing Library, más el script que el plan llama `npm --prefix frontend run test -- policies`.

Por qué: sin `package.json` no hay comprobación de tipos ni de DOM. Las 8 pruebas de Node cubren la máquina de estados, no el clic en la pantalla.

Cómo comprobarlo: montar las páginas y comprobar, en el DOM, que un 422 deja el texto del textarea igual y el botón Activar deshabilitado; que un 409 cambia la comparación y no llama otra vez a activar; que un 401 y un 403 no publican; que un 503 conserva el borrador.

Qué se rompe si falta: el editor puede estar bien en la lógica y mal en el foco, el teclado o el contraste, y nadie lo ve.

### 2. Registrar las pantallas sin editarlas

Qué hace falta: rutas del shell hacia los exports de `frontend/src/features/policies/index.ts`.

- `PolicyListPage` con `client`, `canEdit` y `onEdit`.
- `PolicyEditorPage` con `client`, `policyId` y `canAdmin`.

`canEdit` y `canAdmin` solo cambian los botones. La API sigue siendo quien autoriza. Si los datos vienen de MSW, pasar `exampleData` para mostrar `DATOS DE EJEMPLO`. En la demo final ese indicador no debe aparecer.

Por qué: el shell, la navegación y los tokens globales son de P4. El manual dice que P4 enruta las pantallas de P2 por las interfaces exportadas y no edita la lógica interna.

Cómo comprobarlo: con teclado se llega al textarea, a Validar, a Guardar y a Activar. Escape cierra la confirmación. El error de validación está en un `role="alert"` asociado al textarea. La comparación nombra reglas nuevas, retiradas y modificadas antes de confirmar, y el texto de confirmación dice el `policy_id`, la versión nueva y la que estaba activa.

Qué se rompe si falta: la pantalla existe y no se puede abrir, o P4 copia el editor y las dos copias divergen.

### 3. Auditoría visible del evento `policy_activated`

Qué hace falta: mostrar en la auditoría el `policy_id`, la versión, el checksum y el actor, sin reconstruir el permiso a partir del color de un badge. El tipo de evento ya está en el contrato: `policy_activated`.

Por qué: la cadena de hashes y la pantalla de auditoría son de P4. Persona 2 solo emite el hecho de la activación.

Cómo comprobarlo: después de activar `demo-policy` versión 1, el detalle de auditoría enseña el mismo checksum que `GET /api/v1/policies/demo-policy/versions/1`.

## Acuerdos que todavía no están en el contrato

Estos nombres los usa la API de políticas porque el contrato no les dio un `error.code`. No son reason codes de `DecisionResult`. Hay que aceptarlos en `docs/API_CONTRACTS.md`, que custodia P1, antes de generar OpenAPI.

| Situación | HTTP | `error.code` usado ahora | Por qué este nombre |
|---|---|---|---|
| No hay sesión | 401 | `UNAUTHENTICATED` | El contrato dice 401 y no nombra el código. |
| Rol o tipo de credencial incorrecto, o CSRF ausente | 403 | `FORBIDDEN` | El contrato dice 403 y no nombra el código. |
| La versión no existe | 404 | `NOT_FOUND` | El contrato ya prevé 404 para un recurso no visible. |
| Crear una versión que ya existe | 409 | `CONFLICT` | El contrato pide 409 y no dice el código. No es `STALE_POLICY`: la versión no está obsoleta, está repetida. |
| Activar con `expected_active_version` distinto | 409 | `STALE_POLICY` | Este sí está en el contrato. |
| Documento inválido | 422 | `POLICY_INVALID` | Está en el contrato. Validar no activa. |
| Cuerpo mayor de 64 KiB | 413 | `POLICY_INVALID` con detalle `max_bytes` | El estado HTTP es el del contrato. No se añadió un código nuevo para el tamaño. |
| Auditoría obligatoria fallida | 503 | `AUDIT_UNAVAILABLE` | Está en el contrato. No queda activación parcial. |
| Repositorio ilegible | 503 | `AUTHORIZATION_UNAVAILABLE` | Está en el contrato. No se ejecuta la herramienta. |

El checksum de una política es el SHA-256, en hexadecimal y en minúsculas, del JSON canónico: UTF-8, claves ordenadas, sin espacios, cadenas NFC, sin números reales. No es el RFC 8785 completo. P3 y P4 deben guardar ese hexadecimal tal cual. Si cada uno calcula el digest con otro orden de claves, las aprobaciones caducan siempre.

`POST /api/v1/policies/{id}/versions` recibe el documento JSON ya validado, no el sobre `{format, content}`. El sobre es solo de `POST /api/v1/policies/validate`, para que el servidor vea las claves duplicadas antes de que el framework las pierda. El editor valida YAML o JSON y después guarda el `normalized_policy`.

## Orden recomendado para no rehacer trabajo

1. P1 publica el lock y la migración usando `schema.sql`.
2. P3 implementa `actor_provider` y llama a `evaluate` con el snapshot de `get_active_snapshot`.
3. P4 monta las dos páginas y ejecuta las pruebas de navegador.
4. P3 invalida la aprobación cuando `same_policy_binding` es falso.
5. Solo entonces el runner de P1 puede afirmar S01–S10. Hasta ese momento, la tabla de `policies/examples/README.md` es la expectativa del motor, no un receipt del ejecutor.

## Lo que no hay que pedir

- No hace falta otro evaluador dentro del gateway. Usar `wallba.policy.evaluate`.
- No hace falta editar `policies/demo.yaml` para cambiar una decisión: se publica otra versión.
- No hace falta un editor tipo IDE. El textarea y la validación del servidor son el alcance del MVP.
- No hace falta SMTP, SQL libre ni rutas de disco. Esos parámetros los rechaza el esquema.
- No hace falta que Persona 2 vuelva a implementar la sesión, el shell ni Alembic cuando los otros entreguen su parte: los puertos ya tienen sitio para enchufarlos.
)
