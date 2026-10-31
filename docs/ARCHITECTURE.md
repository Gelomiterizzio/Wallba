# Arquitectura de WALLBA

Un backend modular contiene control, políticas y auditoría; un proceso separado contiene herramientas. La separación del ejecutor es necesaria: una convención de imports en un monolito no impide el bypass de un agente comprometido. No se necesita una red de microservicios para separar este límite.

```mermaid
flowchart LR
  H[Humano] --> UI[React dashboard]
  UI --> API[API FastAPI y autenticación P3]
  A[Agente aislado P1] --> G[Gateway obligatorio P3]
  API --> G
  G --> P[Motor puro P2]
  P --> D{Decisión}
  D -->|DENY| AU[Auditoría P4]
  D -->|REQUIRE_APPROVAL| AP[Aprobaciones P3]
  AP --> G
  D -->|ALLOW| CAP[Capacidad firmada P3]
  G --> CAP
  CAP --> EX[Ejecutor aislado P1]
  EX --> T[Archivos virtuales - outbox - SQLite sintético]
  G --> AU
  API --> DB[(Control SQLite)]
  API --> RUN[Demo runner P1]
```

## Componentes y propiedad

```mermaid
flowchart TB
  P1[Persona 1: contratos, agente, ejecutor, entorno y runner]
  P2[Persona 2: políticas y editor]
  P3[Persona 3: gateway, auth, aprobaciones y su UI]
  P4[Persona 4: auditoría, shell y experiencia visual]
  P1 -->|DTO y fixtures iniciales| P2
  P1 -->|ExecutorPort| P3
  P2 -->|PolicyEvaluator| P3
  P3 -->|AuditSink| P4
  P4 -->|UI primitives| P2
  P4 -->|UI primitives| P3
```

Las flechas indican contratos, no esperas completas. En el primer hito todos obtienen fixtures y puertos falsos. P2/P3 usan HTML accesible mínimo hasta que P4 entregue componentes; no esperan al dashboard.

## Flujo de autorización

```mermaid
flowchart TD
  R[Petición] --> V[Autenticar, validar esquema y resolver recurso virtual]
  V --> C[Contexto confiable y versión activa]
  C --> E[Evaluación pura]
  E -->|error o sin regla| DENY[DENY sin side effect]
  E -->|DENY| DENY
  E -->|REQUIRE_APPROVAL| WAIT[Persistir pendiente y retornar 202]
  E -->|ALLOW| CLAIM[Revalidar y reclamar ejecución atómicamente]
  WAIT --> HUMAN[Humano autorizado aprueba]
  HUMAN --> CLAIM
  CLAIM --> AUD[Persistir intención auditada]
  AUD --> EX[Ejecutor valida capacidad, nonce y digest]
  EX --> RESULT[Resultado y recibo persistidos]
```

## Interacción del agente

```mermaid
sequenceDiagram
  participant A as ScriptedAgent
  participant G as Gateway
  participant P as PolicyEvaluator
  participant X as Executor
  participant U as AuditSink
  A->>G: ToolCall + bearer scoped
  G->>P: CanonicalRequest + TrustedContext
  P-->>G: DecisionEnvelope
  G->>U: authorization_decided
  alt DENY
    G-->>A: blocked + reason_code
  else ALLOW
    G->>X: request + signed capability
    X-->>G: ExecutionReceipt
    G->>U: execution_completed
    G-->>A: sanitized result
  end
```

## Despliegue local

### Estados de una solicitud

```mermaid
stateDiagram-v2
  [*] --> RECEIVED
  RECEIVED --> DENIED: política o scope deniega
  RECEIVED --> PENDING_APPROVAL: requiere humano
  RECEIVED --> READY: ALLOW
  PENDING_APPROVAL --> READY: aprobación válida
  PENDING_APPROVAL --> REJECTED
  PENDING_APPROVAL --> EXPIRED
  PENDING_APPROVAL --> CANCELLED
  READY --> EXECUTING: claim atómico
  READY --> EXPIRED: snapshot superado
  EXECUTING --> SUCCEEDED: receipt confirmado
  EXECUTING --> FAILED: fallo confirmado sin ambigüedad
  EXECUTING --> UNKNOWN: resultado incierto
  UNKNOWN --> SUCCEEDED: reconciliación por receipt
  UNKNOWN --> FAILED: evidencia confirma fallo
```

No hay transición automática UNKNOWN -> READY. Denegación es una decisión de autorización; FAILED es un resultado de ejecución. Mantener esa distinción en API, métricas y UI.

`web` publica solo `127.0.0.1:8080` y proxifica `/api`; API sin puerto público adicional. `agent` solo llega a API, carece de mounts/credenciales del ejecutor. `executor` comparte red interna con API, sin puertos del host y con filesystem read-only salvo sandbox sintético y journal. El runner baseline usa otro ejecutor y volúmenes desechables, activados por perfil Compose `demo`, sin identidad válida para el ejecutor protegido. No hay flag público `firewall=false` sobre recursos protegidos.

El host administrador puede acceder a contenedores y secretos: la garantía no incluye root. No montar Docker socket ni directorios del usuario. Los ejemplos de comandos serán del entorno ficticio; destruir una demo requiere run_id y volumen con label del proyecto.

## Estructura propuesta de código (aún no creada)

```text
backend/wallba/
  contracts/        # P1 DTO base; revisión P2/P3/P4
  foundation/      # P1 app factory, config y DB
  agent/           # P1 simulador y adapter live opcional
  executor/        # P1 herramientas y servicio interno
  demo/            # P1 fixtures, runner, comparación
  policy/          # P2 parser/evaluator/repository/API
  auth/            # P3 sesiones y bearer
  gateway/         # P3 enforcement y ejecución
  approvals/       # P3 state machine y API
  observability/   # P4 auditoría/métricas/read API
frontend/src/
  app/             # P4 shell/routing/provider
  components/      # P4 primitives accesibles
  features/
    policies/      # P2
    approvals/     # P3
    dashboard/ agents/ audit/ playground/ attack-matrix/ # P4
contracts/         # P1 OpenAPI, ejemplos y cliente generado
infra/             # P1 Compose, Dockerfiles
policies/          # P2 políticas de ejemplo
tests/             # Cada persona posee su subdirectorio
```

Futuro: PostgreSQL y múltiples workers, OIDC, adapters reales, política externa, exportación WORM. Cada incremento requiere nuevo threat model; no se promete que el MVP ya lo soporte.

[Seguridad](SECURITY_MODEL.md) · [Contratos](INTEGRATION_CONTRACTS.md) · [Índice](../README.md)
