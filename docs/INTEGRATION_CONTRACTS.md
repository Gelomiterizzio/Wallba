# Contratos internos e integración

Este documento fija puertos antes del código. Dueño P1, revisión por los cuatro. [API](API_CONTRACTS.md) manda sobre wire types. Los refinamientos de manuales personales no pueden cambiar unilateralmente estos contratos.

## Puertos

| Puerto | Firma conceptual | Implementa / consume |
|---|---|---|
| AgentAdapter | `next_calls(scenario, tool_results) -> list[ToolCall]` | P1 / runner P1 |
| ToolGateway | `submit(call, principal, idempotency_key) -> RequestView` | P3 / agente P1 |
| PolicyEvaluator | `evaluate(canonical_request, trusted_context, policy_snapshot) -> DecisionEnvelope` | P2 / gateway P3 |
| PolicyRepository | `get_active() -> PolicySnapshot; activate(version, expected_active_version)` | P2 / gateway P3 |
| ApprovalService | `create(snapshot); approve(id, principal, expected_version, reason); reject; cancel; expire` | P3 / API P3 |
| ExecutorPort | `execute(canonical_request, capability) -> ExecutionReceipt; receipt(execution_id)` | P1 / gateway P3 |
| AuditSink | `append(event, transaction) -> event_id` | P4 / todos |
| DemoRunner | `run_pair(scenario_id, seed) -> DemoRun` | P1 / UI P4 |

`trusted_context` contiene principal_id, agent_id autenticado, roles, environment_id, server_time, resource_version y risk calculado. Prohibido derivarlos de instrucciones del agente. Motor puro sin IO, red, reloj implícito, LLM ni side effects. Riesgo: record.delete HIGH, email.send HIGH, db.query LOW, file.read LOW público/HIGH restringido; argumentos inválidos se rechazan antes de evaluar. CRITICAL reservado para violación de invariante, siempre DENY.

CanonicalRequest incluye ToolCall validada + principal_id + environment_id + resource_version. JSON canónico definido: UTF-8, claves ordenadas recursivamente, sin whitespace, strings NFC, valores solo strings/bools/enteros/listas/objetos/null, sin floats/NaN ni claves duplicadas. Digest SHA-256 sobre esos bytes. `policy_id/version` se enlazan al snapshot de aprobación y capacidad, pero no cambian el digest base del ToolCall. No llamar a esto RFC 8785 si no se implementa ese estándar completo.

## Capacidad interna

Gateway firma HMAC-SHA256 sobre versión, execution_id, request_digest, principal_id, environment_id, resource_version, policy_id/version, expires_at, nonce y audience `wallba-executor`. TTL 30 s, reloj server, tolerancia máxima 2 s. Ejecutor verifica firma en tiempo constante, audience/env, digest y resource_version antes de reclamar nonce. Secreto solo API y ejecutor protegido, rotación coordinada con key_id; agente y baseline no lo conocen. Red interna + autenticación son ambas necesarias. Configurar TLS/mTLS antes de sacar el tráfico del host local.

El ejecutor persiste nonce y execution_id UNIQUE antes del efecto; su journal y cambios SQLite sintéticos se confirman en una transacción cuando sea posible. Email outbox es transaccional, nunca SMTP. Lectura usa catálogo inmutable montado read-only. No se promete exactly-once distribuido: timeout tras envío produce UNKNOWN; gateway consulta receipt, no reintenta a ciegas. Si hay receipt duradero devuelve el mismo. Si no puede demostrar qué ocurrió bloquea repetición y exige reconciliación del operador.

### Punto de autorización y revocación

La lectura de versión activa, reevaluación final y claim se serializan con activación de política en la misma transacción de control (BEGIN IMMEDIATE/CAS). `PolicyRepository` permite leer el snapshot dentro de esa unidad de trabajo. Ese commit es el punto de autorización: cambios de política posteriores afectan claims nuevos; no retiran una capacidad ya emitida de TTL 30 s. La revocación instantánea de operaciones en vuelo no forma parte del MVP y requeriría consulta online del ejecutor. Antes del efecto, el ejecutor comprueba resource_version de forma atómica con el efecto/journal para impedir TOCTOU sobre datos. La UI y la demo deben describir este límite, sin prometer revocación retroactiva.

## Eventos de auditoría

```json
{
 "schema_version":"1", "event_id":"fixture-event-id", "sequence":1,
 "event_type":"authorization_decided", "occurred_at":"2026-10-31T12:00:00Z",
 "request_id":"fixture-request-id", "run_id":null, "principal_id":"demo-reader",
 "agent_id":"demo-agent", "environment_id":"protected-fixture",
 "tool":"record.delete", "resource_id":"table:demo-records",
 "request_digest":"sha256-fixture", "decision":"DENY", "risk":"HIGH",
 "policy_id":"demo-policy", "policy_version":1, "reason_code":"RULE_DENY",
 "execution_id":null, "evidence_id":null, "previous_hash":"genesis", "event_hash":"sha256-fixture"
}
```

IDs ilustrativos no son UUID válidos de producción. Esquema real valida UUID. Tipos: request_received, authorization_decided, approval_created/approved/rejected/expired/cancelled, execution_claimed/completed/failed/unknown, policy_activated, demo_started/completed. P3 publica transición y evento dentro de la misma transacción SQLite usando AuditSink P4; no hay bus externo. P1 publica receipt y demo events por el puerto. Si falla la escritura de intención auditada no ejecutar. Si falla auditar el resultado después del efecto, conservar receipt y reconciliar como UNKNOWN hasta recuperar trazabilidad. No reportar ausencia de efecto por una falla de logs.

## Mocks y fixtures al comienzo

P1 entrega `contracts/examples/` con call permitida/denegada/pendiente y errores 401/403/409/422/503, seed estable y manifest esperado. P2 implementa FakePolicyEvaluator que retorna cada decisión por fixture sin presentarse como motor real. P3 implementa FakeExecutorPort con contador y retraso configurable; P4 usa MSW con esos mismos JSON y badge `DATOS DE EJEMPLO`. Ningún mock activa producción, se selecciona solo en test/dev y falla build de demo final si sigue activo.

## Integración progresiva

1. Aprobar DTO y ejemplos sin esperar módulos completos; P1 publica snapshot de contrato.
2. Cada persona trabaja contra su puerto y contract tests. UI policies/approvals usa primitivas mínimas o mocks de componentes hasta el shell.
3. Conectar PolicyEvaluator a Gateway; comprobar DENY con contador ejecutor cero.
4. Conectar ExecutorPort real aislado; comprobar permisos/redes/capacidad y receipt.
5. Integrar AuditSink transaccional y UI de aprobaciones; probar dos aprobaciones simultáneas.
6. Integrar runner paired y UI; E2E sin mocks sobre recursos sintéticos.

Bloqueo: registrar ID, entrada faltante, dueño y siguiente acción; avanzar tarea independiente sin inventar contrato. Conflicto: detener solo las ediciones que colisionan, no sobrescribir; el propietario resuelve mediante PR pequeño. Cambio incompatible: RFC con ejemplo antes/después, consumidor afectado y prueba, aprobación de dueños; actualizar versión, mocks, docs y generados juntos.

[Roadmap](ROADMAP.md) · [Índice](../README.md)
