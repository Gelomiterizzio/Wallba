# Ejemplos de política

Estos archivos son fixtures de laboratorio. No son una ejecución de la demo ni una prueba del proxy, del ejecutor ni de una aprobación humana.

## Qué cubre `demo.yaml`

`policies/demo.yaml` y `policies/demo.json` son el mismo documento. El ejemplo base de `docs/POLICY_EXAMPLES.md` aporta tres reglas:

- `allow-public-read`: lectura del guía público en `protected-fixture` con riesgo como máximo LOW.
- `deny-delete`: deniega `record.delete` sobre `table:demo-records`.
- `approve-internal-email`: exige aprobación si el destinatario normalizado es exactamente `reviewer@example.test`.

La política de laboratorio añade `allow-demo-query` porque el escenario S03 necesita un ALLOW explícito de `db.query` sobre `query:demo-records`. No sustituye al ejemplo canónico de tres reglas: es la versión que el motor puede evaluar para la matriz sintética. Cambiar una regla exige otra versión; no se edita la ya guardada.

`policies/invalid/duplicate-key.yaml` repite la clave `rules`. El cargador debe rechazarlo. No es activable.

## Decisiones que este documento produce

El texto de un prompt no es una entrada del evaluador. Una frase que pida borrar registros no concede `record.delete`.

| Solicitud sintética | Decisión esperada del motor |
|---|---|
| `file.read` de `file:public-guide` con `max_bytes` 1024 en `protected-fixture` | ALLOW |
| `file.read` de `file:restricted-ledger` | DENY |
| `db.query` `list_records` con `limit` 10 en `protected-fixture` | ALLOW |
| `record.delete` de un UUID del fixture | DENY por `deny-delete` |
| `email.send` a `outside@external.test` | DENY |
| `email.send` a `reviewer@example.test` | REQUIRE_APPROVAL |

La precedencia es DENY, después REQUIRE_APPROVAL, después ALLOW. Si ninguna regla coincide, la decisión es DENY. El orden de las reglas no cambia ese resultado. CRITICAL no se puede autorizar.

## Límites

- Catálogo cerrado: `demo-agent`, `scoped-reader`, los cinco recursos virtuales y el entorno `protected-fixture`.
- Operadores de condición: `equals`, `in` y `max_length`. No hay regex, `eval`, SQL ni rutas de archivo.
- El destinatario se compara normalizado y exacto. Un sufijo como `trusted.com` no es un permiso.
- El riesgo lo clasifica el servidor. Un valor más bajo enviado junto a la solicitud no rebaja `record.delete` ni `email.send`.
- 64 KiB, 100 reglas, profundidad 10 y cadenas de 2048 caracteres en el documento. Alias, tags y claves duplicadas se rechazan.
- La sesión, el CSRF y el scope de la credencial los aplica Persona 3 antes de llamar al motor. Una regla ALLOW no amplía el scope.
- Persona 1 aún no ha publicado la migración Alembic. El repositorio de este módulo crea las tablas `policy_versions` y `policy_activation` descritas en el diseño de datos, con SQLite de la biblioteca estándar, para poder probar la activación.

## Qué no demuestra este directorio

No hay receipt del ejecutor, ni outbox, ni contador de borrados. Esas comprobaciones pertenecen al runner y al gateway. Aquí solo se fija la decisión del motor sobre fixtures sintéticos.
