# Contratos API v1

Estado: especificación previa a implementación. P1 custodia DTO/OpenAPI; cada endpoint tiene dueño. Los ejemplos son fixtures, no ejecuciones. Base `/api/v1`. JSON UTF-8, snake_case, UUID, timestamps UTC RFC3339; frontend convierte zona solo para mostrar. `additionalProperties=false`, strings NFC y longitudes acotadas; no coerción de booleanos/números. Errores no contienen stacktraces, tokens, contenido de archivos ni correos completos.

## DTO compartidos

```typescript
type ToolName = 'file.read' | 'email.send' | 'record.delete' | 'db.query';
type Risk = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
type Decision = 'ALLOW' | 'DENY' | 'REQUIRE_APPROVAL';
type RequestState = 'RECEIVED' | 'DENIED' | 'PENDING_APPROVAL' |
 'READY' | 'EXECUTING' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN' |
 'REJECTED' | 'EXPIRED' | 'CANCELLED';
interface ToolCall {
 request_id: string; agent_id: string; tool: ToolName;
 operation: 'read' | 'send' | 'delete' | 'query';
 resource_id: string; parameters: Record<string, unknown>;
}
interface DecisionEnvelope {
 request_id: string; decision: Decision; reason_code: string;
 matched_rule_ids: string[]; policy_id: string | null;
 policy_version: number | null; risk: Risk;
}
interface ExecutionReceipt {
 execution_id: string; request_id: string; state: 'SUCCEEDED'|'FAILED'|'UNKNOWN';
 result_digest: string | null; effect_count: number | null;
 evidence_id: string; completed_at: string | null;
}
```

`Record` es abreviatura de documentación: el esquema real es una unión discriminada cerrada por `tool`; los campos siguientes son exhaustivos. El servidor deriva principal_id, roles, environment_id, riesgo y hora; rechaza esos campos si llegan del cliente. `agent_id` debe coincidir con bearer o con el agente elegido por un operador autorizado. `operation` debe corresponder exactamente al tool.

| Tool y operation | resource_id | parameters admitidos | Resultado saneado |
|---|---|---|---|
| file.read / read | `file:public-guide` o `file:restricted-ledger` | `{max_bytes: integer 1..16384}` | content truncado, content_digest y bytes |
| email.send / send | `mailbox:demo-outbox` | `{to: string, subject: string<=120, body: string<=4096}` | message_id y delivery:`SIMULATED` |
| record.delete / delete | `table:demo-records` | `{record_id: UUID}` | deleted_count:0..1 y receipt |
| db.query / query | `query:demo-records` | `{query_id:'list_records'|'count_records', limit:integer 1..100}` | rows permitidas o count |

`to` pertenece al dominio ficticio `.test`, jamás se entrega a SMTP. El baseline puede simular un destinatario prohibido por política sin enviar nada real. No existen parámetros SQL, filepath, command ni arbitrary_url. IDs de fixtures estables, documentos restringidos identificados por catálogo. Rechazar controles, bytes nulos y formas ambiguas. `max_bytes` no es permiso para un recurso diferente.

## HTTP común

Listado: `{items:[], next_cursor:null}`; cursor opaco, límite 1..100 (default 50), orden `(created_at,id)` descendente y filtros tipados. Invalid cursor 422. DELETE público sobre recursos reales no existe.

Error: `{error:{code,message,request_id,details:[]}}`. `details` solo `{field,code}`. Códigos HTTP: 401 sin identidad; 403 sin rol o DENY; 404 recurso no visible; 409 conflicto de estado/idempotencia/versión; 413 payload; 422 esquema; 429 límite; 503 autorización/auditoría/ejecutor indisponible. Una aprobación pendiente usa 202, no un éxito de herramienta. `UNKNOWN` puede retornarse en el recurso de ejecución; no ocultarlo tras 500 genérico.

## Endpoints y autorización

| Método y ruta | Dueño | Entrada / salida | Acceso y errores particulares |
|---|---|---|---|
| POST /auth/login | P3 | username/password -> sesión + csrf_token + roles | humano, rate limit, 401 sin revelar usuario |
| POST /auth/logout | P3 | vacío -> 204 revoca sesión | humano + CSRF |
| GET /auth/me | P3 | identidad/roles/csrf_token | sesión; 401 |
| GET /agents | P1 | listado id/name/tools/status | viewer |
| GET /agents/{id} | P1 | detalle + resource scopes | viewer |
| POST /agent-runs | P1 | scenario_id -> run_id | operator, demo only; no texto libre que fuerce bypass |
| GET /agent-runs/{id} | P1 | estado y tool request_ids | viewer |
| POST /tool-requests | P3 | ToolCall -> {request_id,state,decision,approval_id,execution_id} | bearer agente o operator; Idempotency-Key requerido |
| GET /tool-requests/{id} | P3 | estado, decisión y receipt si existe | agente propietario o viewer |
| GET /approvals | P3 | filtros status/agent_id/risk -> página | viewer |
| GET /approvals/{id} | P3 | snapshot saneado, digest, expiry, estado | viewer |
| POST /approvals/{id}/approve | P3 | {expected_version,reason} -> estado | approver + CSRF, no solicitante; 409/410 |
| POST /approvals/{id}/reject | P3 | {expected_version,reason} -> estado | approver + CSRF; reason 1..500 |
| POST /approvals/{id}/cancel | P3 | {expected_version,reason} -> estado | operator propietario o approver + CSRF |
| GET /policies | P2 | política activa y versiones | viewer |
| GET /policies/{id}/versions/{version} | P2 | documento inmutable + checksum | viewer |
| POST /policies/validate | P2 | {format:'yaml'|'json',content:string} -> {valid,errors,normalized_policy} | policy_admin + CSRF; jamás activa |
| POST /policies/{id}/versions | P2 | documento válido -> nueva versión | policy_admin + CSRF; 409 versión existente |
| POST /policies/{id}/activate | P2 | {version,expected_active_version} -> active version | policy_admin + CSRF; CAS y evento |
| GET /dashboard | P4 | counters, by_decision, by_risk, recent, as_of | viewer; filtros from/to UTC |
| GET /audit | P4 | filtros tool/agent_id/decision/risk/from/to/request_id -> página | viewer |
| GET /audit/{event_id} | P4 | detalle saneado + hashes/sequence | viewer |
| GET /audit/export | P4 | JSONL saneado + manifest digest | viewer; rango obligatorio, máximo 10k |
| GET /scenarios | P1 | catálogo y expectativas claramente rotuladas | viewer |
| POST /demo-runs | P1 | {scenario_id,seed,mode:'paired'} -> 202 {run_id,status} | operator + CSRF, demo profile; 409 otro run activo |
| GET /demo-runs/{id} | P1 | estados baseline/protected y receipt/evidence refs | viewer |
| GET /demo-runs/{id}/evidence | P1 | manifest de inputs/digests/efectos/event_ids | viewer |
| GET /matrix | P1 | filas probadas de runs, inicialmente [] | viewer; no rellenar con expectativas |
| GET /health/live | P1 | {status:'ok'} sin secretos | loopback |
| GET /health/ready | P1 | DB/policy/executor readiness booleans | loopback; 503 si no está listo |

El dashboard agrega solo eventos `protected` por defecto; baseline necesita filtro explícito y badge. Acceso al ejecutor interno no forma parte de esta API. No hay endpoint humano para ejecutar parámetros editados después de aprobar.

### Reason codes canónicos

| Código | Significado / HTTP cuando corresponde |
|---|---|
| RULE_ALLOW | Regla permite; 200 con estado/receipt |
| RULE_DENY | Regla deniega; 403 sin despacho |
| DEFAULT_DENY | Sin regla aplicable; 403 |
| APPROVAL_REQUIRED | Crear pendiente; 202 |
| POLICY_MISSING | No hay política activa; 503 fail closed |
| POLICY_INVALID | Documento inválido; admin 422; evaluación activa corrupta 503 |
| AUTHORIZATION_UNAVAILABLE | Evaluador/repositorio no disponible; 503 |
| SCOPE_DENIED | Credencial no habilita tool/recurso; 403 |
| DIGEST_MISMATCH | Snapshot modificado; 409 |
| STALE_POLICY / STALE_RESOURCE | Snapshot superado; 409, approval EXPIRED |
| APPROVAL_EXPIRED | Hora límite alcanzada; 410 |
| APPROVAL_ALREADY_CONSUMED | Reutilización; 409 |
| AUDIT_UNAVAILABLE | No se pudo persistir intención; 503 sin ejecución |
| EXECUTION_UNKNOWN | Efecto incierto; estado UNKNOWN y reconciliación |

Estos reason codes complementan el formato común; errores de esquema usan VALIDATION_ERROR y detalles por campo. No usar POLICY_UNAVAILABLE como alias. Validación administrativa inválida retorna 422 con `error.code=POLICY_INVALID` y detalles; validación correcta retorna 200 `{valid:true,errors:[],normalized_policy}`. No activar en ninguno de los dos casos.

## Identidad e idempotencia

Sesión humana opaca 256 bits, hash almacenado, expiry 8 h absoluta y 30 min inactiva. Cookie HttpOnly SameSite=Strict; Secure obligatorio salvo loopback HTTP local documentado. Rotar en login, eliminar en logout. CSRF sincronizado + validación Origin para toda mutación humana. Bearer aleatorio de agente en secret mount, hash en almacenamiento; scopes por agent/tools/resources, nunca roles humanos. Passwords con Argon2id, usuarios demo creados mediante seed local y contraseña aleatoria fuera de Git. Agente no tiene password de aprobador.

`Idempotency-Key` UUID en `/tool-requests`, scoped por principal. Misma clave y payload canónico devuelve estado persistido; distinta carga -> 409. `request_id` único y ligado al principal; colisón ajena no revela datos. Aprobar usa `expected_version`; CAS previene doble click y carreras. `Idempotency-Key` no autoriza repetir un efecto ni reemplaza el nonce del ejecutor.

## Compatibilidad y generación

P1 materializará `contracts/openapi.json`, `contracts/examples/*.json`, `frontend/src/api/generated.ts` y fixtures desde DTO Python; cliente generado no se edita a mano. OpenAPI diff en CI. Cambio compatible agrega campo opcional de respuesta; enum nuevo exige revisión de UI exhaustiva. Cambio de semántica, campos obligatorios o autorización requiere propuesta conjunta y `/v2` si no hay migración coordinada. P1 integra el cambio, P2/P3/P4 revisan según impacto. [Puertos](INTEGRATION_CONTRACTS.md) y [propiedad](OWNERSHIP_MATRIX.md).
