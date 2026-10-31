# Estrategia de pruebas y evidencia

Estado: pruebas de producto planificadas, **no ejecutadas**. Durante esta entrega solo se validan metadatos, estructura, enlaces y configuración documental. Cada propietario escribe y ejecuta pruebas de su dominio; P4 coordina E2E/visual, no absorbe la calidad del resto.

| Nivel | Casos mínimos | Dueño y evidencia |
|---|---|---|
| Unit foundation/agent/tools | config fail closed; 4 tools, query IDs, fixtures, script trace | P1 pytest + seed/receipt |
| Unit policy | JSON/YAML iguales, tipos estrictos, sin regla, precedencia, orden independiente, límites | P2 pytest/Hypothesis y semillas |
| Unit gateway/auth | scopes, token inválido, roles, CSRF/Origin, idempotency collision | P3 pytest/httpx |
| Unit approval | expiración fake clock, digest mismatch, rol distinto, cancel/reject terminal | P3 state table y comandos |
| Unit audit/UI | redaction, chain, agregaciones, loading/empty/error/stale | P4 pytest/Vitest |
| Contratos API | examples contra schema, HTTP status/error, cliente generado, unknown fields | P1 coordina; cada dueño endpoint |
| Integración | policy real + gateway + isolated executor, counter=0 al DENY | P3 con P1, logs y journal |
| Persistencia | migra empty/prior, restart, constraints, rollback, receipts | Cada dueño; P1 configura fixtures |
| Carreras | approve dos workers/request handlers, mismo nonce, activate vs claim, resource_version | P3/P2/P1; barreras reproducibles |
| Fallos | DB locked/down, policy corrupta, audit unavailable, timeout antes/después side effect | P3/P4/P1; UNKNOWN y no blind retry |
| Aislamiento | agente sin mount/secret, ejecutor sin puerto, bad HMAC/audience/env/TTL | P1/P3; pruebas dentro red Compose |
| Adversariales | S01–S10 más path traversal, SQL/raw parameters, role spoofing | P2 diseño; dueños implementan |
| Frontend/accesibilidad | teclado, foco, etiquetas, contrastes, mobile/zoom, axe | P4 shell; P2/P3 pantallas propias |
| E2E sin mocks | login -> escenario -> deny/approval -> receipt -> audit/matrix | P4 coordina, P1/P2/P3 investigan fallos propios |
| Regresión | bug produce prueba que falla antes y pasa después | Dueño del bug |

## Casos de seguridad obligatorios

Principal agente no puede aprobar, aunque manipule agent_id o role. Policy_admin sin approver no aprueba. Scope deny prevalece ante regla ALLOW. Error del motor no ejecuta. Evento de intención fallido no ejecuta. Cambio de body/env/principal/resource o policy antes del claim invalida approval. Cambio de policy después del claim tiene semántica explícita de capacidad en vuelo TTL30s, no revocación retroactiva. Segundo claim/replay no crea efecto adicional. Record version check atómico en ejecutor rechaza TOCTOU. Reinicio EXECUTING produce reconciliación, nunca reenvío automático. Cadena audit alterada detectada, pero no se presenta como protección contra root.

## Comandos futuros de validación

Después de que P1/P4 implementen entornos: `uv run pytest tests/`; `npm --prefix frontend run lint`; `npm --prefix frontend run typecheck`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run build`; `npm --prefix frontend run test:e2e`; `docker compose --profile demo up --build`. Son interfaces propuestas que P1/P4 deben materializar en README, no comandos disponibles ahora. No aprobar una entrega solo porque esos comandos fueron escritos.

## CI propuesta

P1 mantiene workflow: valida plan/links, backend lint/type/unit, frontend lint/type/unit/build, OpenAPI diff, integración aislada y E2E Chromium; dependency/security scan con resultados revisados. Los responsables aportan sus comandos y fixtures. Secretos de demostración efímeros; no publicar DB completas ni tokens como artifacts. Separar tests lentos en job propio sin omitir controles obligatorios del release. No se crea workflow ejecutable antes de aprobar implementación.

## Evidencia reproducible

Guardar comando exacto, commit (o null si no existe), timestamp UTC, versiones/OS, configuración saneada, seed, policy checksum, fixture digest, exit code, salida relevante y manifest. Screenshots incluyen viewport y run_id; no prueban por sí solas autorización. Usar reloj inyectado y barreras de concurrencia, no sleeps arbitrarios. Aserciones sobre counters/journal/recursos, no solo status HTTP.

## Gate de entrega

Todos los criterios de tareas cumplidos; suites pertinentes ejecutadas; S01–S10 observados con evidencia o N/A fundamentado; cero hallazgos críticos/altos de autorización sin resolver; UNKNOWN reportado honestamente; sin MSW en demo final; navegación teclado y contrastes revisados; migración/recovery probado; instrucciones de seed/reset reproducibles. Si un check no pudo ejecutarse, estado pendiente y bloqueo explícito, nunca PASS.

[Demo](DEMO_SCENARIOS.md) · [Índice](../README.md)
