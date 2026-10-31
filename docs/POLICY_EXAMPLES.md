# Políticas de ejemplo y validación

Estos ejemplos son especificaciones de fixtures, no políticas activadas. P2 materializa esquemas y tests. Envelope `schema_version:'1'`, policy_id, version entero >=1, rules no vacías (máximo 100). IDs únicos. effects ALLOW/DENY/REQUIRE_APPROVAL. agents/tools/resources listas exactas no vacías sin glob. Las condiciones omitidas no restringen; una condición presente debe ser conocida y del tipo correcto. No existen scripts, expresiones arbitrarias o interpolación de entorno.

Condiciones iniciales: `principal_roles` lista de roles humanos o `agent`; `context_environments` lista de environments confiables; `risk_at_most` enum; `parameters` mapa de condiciones cerradas según herramienta. Operadores admitidos: equals, in y max_length en campos previstos; no generalizar acceso mediante dot-path. Para `to`, usar lista exacta, sin regex. Todas se evalúan en AND. `risk_at_most` usa orden LOW < MEDIUM < HIGH < CRITICAL; ninguna política autoriza CRITICAL.

```yaml
schema_version: '1'
policy_id: demo-policy
version: 1
rules:
  - id: allow-public-read
    effect: ALLOW
    agents: [demo-agent]
    tools: [file.read]
    resources: ['file:public-guide']
    conditions:
      context_environments: [protected-fixture]
      risk_at_most: LOW
  - id: deny-delete
    effect: DENY
    agents: [demo-agent]
    tools: [record.delete]
    resources: ['table:demo-records']
  - id: approve-internal-email
    effect: REQUIRE_APPROVAL
    agents: [demo-agent]
    tools: [email.send]
    resources: ['mailbox:demo-outbox']
    conditions:
      parameters:
        to:
          in: [reviewer@example.test]
```

JSON equivalente completo (mismo resultado de normalización):

```json
{
  "schema_version": "1",
  "policy_id": "demo-policy",
  "version": 1,
  "rules": [
    {"id":"allow-public-read","effect":"ALLOW","agents":["demo-agent"],"tools":["file.read"],"resources":["file:public-guide"],"conditions":{"context_environments":["protected-fixture"],"risk_at_most":"LOW"}},
    {"id":"deny-delete","effect":"DENY","agents":["demo-agent"],"tools":["record.delete"],"resources":["table:demo-records"]},
    {"id":"approve-internal-email","effect":"REQUIRE_APPROVAL","agents":["demo-agent"],"tools":["email.send"],"resources":["mailbox:demo-outbox"],"conditions":{"parameters":{"to":{"in":["reviewer@example.test"]}}}}
  ]
}
```

Para S03 agregar regla explícita ALLOW para db.query/query:demo-records; se conserva versión distinta si cambia contenido. Para S06 usar correo permitido que requiere aprobación. Para S05 `outside@external.test` no coincide y recibe DEFAULT_DENY. No colocar DENY general de email que impediría S06 por precedencia.

Validar safe loader sin objetos Python, claves duplicadas, aliases/anchors rechazados, profundidad máxima 10, 64KiB, claves desconocidas y operadores incompatibles. Entregar errores con ubicación y código, sin stacktrace. Separar parseo, esquema, validación semántica y advertencias de solapamiento. La intersección de listas exactas permite detectar conflictos obvios; conflictos condicionales complejos se reportan conservadoramente, no se promete un solver completo.

Activación: insertar versión inmutable y checksum; comparar expected_active_version, activar en transacción, emitir evento. Un archivo inválido retorna 422 y deja intacta activa previa. Editar UI crea nueva versión; nunca actualiza filas existentes. P2 prueba JSON/YAML equivalentes, orden de reglas, defaults, tipos erróneos, política vacía, múltiples decisiones y scopes externos.

[Modelo de seguridad](SECURITY_MODEL.md) · [Índice](../README.md)
