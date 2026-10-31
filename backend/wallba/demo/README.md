# Laboratorio de demostración (P1)

Compara la misma `ToolCall`, con la misma seed y el mismo fixture, en dos entornos sintéticos separados: `baseline` (sin firewall) y `protected` (por el gateway). Todo el contenido es ficticio; el correo es un outbox `SIMULATED`.

**Límites.** El agente es un guion determinista, no un LLM: S08 demuestra que se bloquea una intención inducida, no la robustez general de un modelo. La matriz está vacía hasta que haya runs reales. Con dobles de P2/P3/P4 los resultados sirven para desarrollo y no son evidencia de protección real.

## Puesta en marcha

Desde la raíz del repositorio:

```bash
python scripts/generate_dev_secrets.py     # crea secrets/ fuera de Git (carpeta 0700); nunca sobrescribe
uv sync --project backend --frozen         # entorno local desde el lock
uv run --project backend pytest tests      # sin Docker, test_live_isolation queda SKIPPED

WALLBA_DEMO_ENABLED=true docker compose -f infra/compose.yaml --profile demo up -d --build
```

Solo `web` publica un puerto (`127.0.0.1:8080`), con el perfil `web`, cuando exista el frontend de P4. Sin los puertos de P2, P3 y P4 la API arranca pero sus rutas responden `503`: esto es el fallo cerrado esperado, no un error.

## Conexión de los demás módulos

`create_app` recibe `Integrations(authorizer, gateway, audit, harness, policy_ready, extra_routers)`. Cada dueño aporta la implementación de su puerto de `wallba/contracts/ports.py`. `create_app_from_env` debe componerlas al integrar; no existe ningún modo que omita un puerto.

## Estados de un run

| Estado | Significado |
|---|---|
| `RUNNING` | En curso |
| `WAITING_APPROVAL` | Un humano distinto debe decidir; el runner nunca aprueba |
| `WAITING_ADMIN_INPUT` | S09: espera el paso administrativo de P2 |
| `COMPLETED` | Ambos lados observados, o `N/A` con motivo |
| `INCOMPLETE` | Falta una observación; se conserva lo parcial |
| `UNKNOWN` | Efecto incierto: nunca se trata como cero efectos ni se reintenta |

Consultar `GET /demo-runs/{id}` reanuda un run en espera. Un reinicio con un run `RUNNING` lo marca `INCOMPLETE/INTERRUPTED`, sin repetirlo. Tras 15 minutos en espera pasa a `INCOMPLETE`.

## Recuperación

- **Respuesta perdida o timeout:** consultar `GET /internal/receipts/{execution_id}`. Con receipt, ese es el resultado. Sin receipt, conservar `UNKNOWN` y reconciliar; no reenviar con otro nonce.
- **Backup:** `wallba.foundation.database.backup_database(origen, destino)`; nunca sobrescribe.
- **Restore:** `restore_to_copy(backup, destino_nuevo)`; siempre a un archivo nuevo, nunca sobre la base activa. Antes de una migración, hacer backup.
- **Reset de un entorno:** `DELETE /internal/environments/{run_id}` en el ejecutor. Exige un `run_id` UUID y un directorio con la etiqueta de WALLBA, y rechaza el entorno activo. No toca la base de control ni la auditoría.
- **Limpieza total del laboratorio:** `docker compose -f infra/compose.yaml --profile demo down -v` borra solo los volúmenes del proyecto, **incluida la evidencia**: exportarla antes.

## Reproducir una demostración

1. Partir de volúmenes limpios y registrar `WALLBA_GIT_SHA=$(git rev-parse HEAD)`.
2. `POST /api/v1/demo-runs` con `{"scenario_id":"S04","seed":7,"mode":"paired"}` como operator.
3. `GET /api/v1/demo-runs/{id}` y `GET /api/v1/demo-runs/{id}/evidence`.
4. Comprobar en el manifest: decisión `DENY`, `journal_added: 0` y `state_changed: false` en `protected`, y `records_removed: 1` en `baseline`. Que el recurso no cambie no basta por sí solo: hay que ver también el journal.
5. Guardar comando, commit, seed, versiones, exit code y `manifest_digest`.

## Regenerar contratos

```bash
uv run --project backend python scripts/export_contracts.py
npx openapi-typescript@7.4.4 contracts/openapi.json -o frontend/src/api/generated.ts
```

`generated.ts` no se edita a mano. CI falla si `contracts/` difiere del código.
