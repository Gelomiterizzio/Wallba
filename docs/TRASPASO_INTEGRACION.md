# Traspaso de la integración

Estado al 2026-10-31. Rama: `integration/final-four-contributors`, basada en `main` (`ffcc426`). Esta rama no está fusionada y no tiene PR.

## Resumen

- Los aportes de las cuatro personas ya funcionan como un solo sistema en proceso: S01 a S10 pasan por HTTP real, sin dobles.
- **Hay una prueba en rojo:** `test_api_runs_without_ports_of_others_failing_closed`. Hará fallar el job `infra` del CI hasta corregirla.
- `main` sigue con el job `frontend` en rojo hasta que entre esta rama, que trae la corrección del desborde en `/audit`.
- **El sistema de protección de archivos (`wallba.guard`) NO está implementado.** No existe código; abajo solo está su diseño.

## Qué se integró

| Área | Cambio | Archivos |
|---|---|---|
| Auditoría | `AuditFanout` escribe en `AuditWriter` y en el outbox de P3 en la misma transacción | `backend/wallba/observability/adapters.py` |
| Gateway | Usa la auditoría conectada, el servicio de políticas real y el router de observabilidad | `backend/wallba/gateway/bootstrap.py`, `service.py` |
| Escenarios | `ControlPlaneHarness`: S09 valida un YAML inválido contra el servicio real y comprueba que el checksum activo no cambie | `backend/wallba/demo/control_plane.py` |
| Semilla | Crea usuarios demo, credencial de `demo-agent` y la política de `policies/demo.yaml`. Es idempotente | `backend/wallba/demo/seed.py` |
| Imagen API | Arranca con `create_app_from_env` e incluye `policies/` | `infra/Dockerfile.api`, `.dockerignore` |
| Login | Tras el POST lee `/auth/me`, porque el login solo devuelve `csrf_token` y `roles` | `frontend/src/app/session.tsx`, `src/api/types.ts` |
| Aprobaciones | `/approvals` monta `ApprovalCenter` de P3; se quitó la pantalla provisional | `frontend/src/app/routes.tsx` |
| CSS | Corrige el desborde de `/audit` en Linux, sin relajar la prueba | `frontend/src/styles/app.css` |
| Pruebas | S01 a S10, auditoría, dashboard, semilla y permisos con el sistema real | `tests/gateway/test_full_system.py` |
| Contratos | Regenerados | `contracts/openapi.json`, `frontend/src/api/generated.ts` |

## Resultados de pruebas

Ejecutadas en Windows sobre `4323883`, salvo Playwright.

| Comprobación | Resultado |
|---|---|
| `pytest` completo, con Docker | 478 pasan, **1 falla**, 1 omitida |
| `vitest` | 66 pasan |
| `npm run test:node` | 8 pasan |
| `npm run build`, `eslint` | Correctos |
| `scripts/validate_plan.py` | PASS |
| Playwright, imagen Linux | 46 pasan. Se ejecutó antes de regenerar los contratos y no se repitió |

**El CI de esta rama no se ha ejecutado:** es la primera vez que se sube.

## Lo que falló

`tests/infra/test_live_isolation.py::test_api_runs_without_ports_of_others_failing_closed`

```text
AssertionError: assert '401' == '503'
```

Causa probable: la prueba espera 503 en `/agents`, de cuando la imagen arrancaba con la factory de P1. Ahora arranca con la de P3, que tiene autenticador real y rechaza con 401 antes de llegar a esa ruta. Sigue cerrando el acceso, pero hay que confirmarlo al corregir la prueba: cambiar la expectativa sin más dejaría de comprobar el caso original.

## Lo que no se ha verificado

- Recorrido completo en navegador con el stack Compose real: login, escenario, auditoría y aprobación.
- Lector de pantalla y zoom al 200 %.
- Estados en `docs/planning/person-*-tasks.json`: no se actualizaron.

## Hallazgos abiertos

1. **Activación de políticas (P2):** se compara solo el número de versión. Con `demo-policy` v1 activa, `expected_active_version=1` permite activar `other-policy` v1 sin conflicto.
2. **`get_active_snapshot` (P2):** abre su propia conexión.
3. **Rama `feature/person-4-dashboard`:** tiene `5951d0f` sin PR. Antes de borrarla, revisar con `git log origin/main..origin/feature/person-4-dashboard`.

## Cómo arrancar

La operación está en `backend/wallba/demo/README.md`. Para crear los datos de demostración:

```bash
python -m wallba.demo.seed [--agent-bearer-file RUTA]
```

Las contraseñas aleatorias se muestran una sola vez. En Git Bash sobre Windows, los montajes de Docker necesitan `MSYS_NO_PATHCONV=1` y `pwd -W`.

## Lo que falta, en orden

1. Corregir la prueba del 503 y comprobar el recorrido con Compose.
2. Abrir el PR de esta rama hacia `main`, ver el CI y fusionar con aprobación.
3. Resolver o reportar el hallazgo de activación de P2.
4. Construir `wallba.guard` y sus pantallas.
5. Escribir `INTEGRACION_FINAL.md` y `SEGURIDAD_Y_PROTECCION.md`, actualizar los estados del plan y hacer el reporte final.

## Diseño de `wallba.guard` (sin implementar)

**Ubicación:** routers en la misma API, activos solo en host mediante `WALLBA_GUARD_ALLOWED_ROOTS` (separada por `os.pathsep`). Vacía significa desactivado: 503 `GUARD_DISABLED`. Reutiliza login y roles de P3: `viewer` lee, `policy_admin` cambia reglas. Usa una base propia `guard.sqlite` en el directorio de datos, fuera del proyecto, y rechaza proyectos que contengan ese directorio. No hay API de contenido de archivos.

| Módulo | Responsabilidad |
|---|---|
| `paths.py` | `canonical_dir`; `relative_to_root` resuelve enlaces, lanza `PathOutsideProject` y en Windows elimina los alias `.env.`, `.env ` y `::$DATA`; `match_key` aplica NFC y casefold en Windows; `is_within` compara por segmentos |
| `classifier.py` | Sin puntuación: el nivel es el de la regla más severa y cada hallazgo la explica |
| `policy.py` | Modos, reglas y `evaluate`, que devuelve allow, observe o deny. Gana la regla más específica. `blocked_inside` cubre operaciones sobre carpetas |
| `scanner.py` | Solo metadatos; no sigue enlaces; salta `.git`, `node_modules`, etc. |
| `store.py` | Proyectos, entradas, reglas, exclusiones, baselines y alertas con dedupe de 60 s |
| `hook.py` | `python -m wallba.guard.hook --db RUTA --agent claude-code`, formato PreToolUse. Falla cerrado si no puede leer la base |
| `shim.py` | `GuardedFiles`: agente instrumentado para pruebas |
| `monitor.py` | Sondeo cada 5 s y sha256 de archivos protegidos; solo metadatos en archivos muy grandes |

**Clasificación:**

| Nivel | Coincide con | Modo recomendado |
|---|---|---|
| CRITICAL | `.env*`, claves (`*.pem`, `*.key`, `id_rsa`), archivos de credenciales, carpetas `.ssh`, `.aws`, `secrets`, `*.tfstate` | `block_access` |
| HIGH | Nombres con secret, token o password; `.github/workflows/*`; bases de datos y respaldos; permisos; datos privados | `block_write` |
| MEDIUM | IaC, Dockerfile, configuración de aplicación | `alert` |

Las plantillas (`.example`, `.sample`) bajan dos niveles y las carpetas de pruebas uno, con la rebaja explicada. El modo es solo una recomendación: no se aplica por sí solo.

**Modos:** `monitor`, `alert`, `block_write` (write y delete), `block_access` (read, write y delete). Regla: `GuardRule(rel_path, is_dir, recursive, mode, allowed_agents)`.

**Hook:**

- Read cuenta como lectura. Write, Edit, MultiEdit y NotebookEdit cuentan como escritura.
- Grep sobre una carpeta con contenido bloqueado se niega; Glob se permite.
- Bash es heurístico y debe declararse como "best effort".
- La salida es `hookSpecificOutput.permissionDecision: "deny"`.
- No se toca la configuración real del usuario: solo se imprime el snippet.
- No se ha probado con un Claude Code real.

**Monitor:** detecta creado, modificado, eliminado y renombrado. Usa `ORIGEN NO DETERMINADO` salvo evidencia de un hook reciente. Alerta de pérdida de cobertura y de fallo del monitor. La verificación completa es manual. No restaura archivos por su cuenta.

**Alertas:** tres tipos separados: intento bloqueado, intento observado y modificación detectada.

**Interfaz:**

- `/protection`: abrir proyecto, hallazgos, árbol con casillas y estado parcial, reglas y snippet del hook.
- `/alerts`: filtros, detalle, marcar como leído y exportar.
- Resumen en el dashboard y tema claro por tokens.

**Límites que hay que declarar:** un agente que corre con el mismo usuario puede saltarse un hook o editar la base. Un monitor no prueba lecturas ni identifica quién hizo un cambio. Una política solo es preventiva si bloquea antes de la operación; si solo observa después, debe decirlo.

## Reglas de trabajo

- Sin push, merge ni despliegue sin aprobación explícita del responsable.
- No descartar cambios locales ni hacer pruebas destructivas sobre archivos reales.
- Sin credenciales ni contenido sensible en registros de eventos.
- Sin números ficticios ni mocks presentados como evidencia. `UNKNOWN` no significa fallo sin efecto.
- No atribuir un cambio a una IA concreta sin evidencia.
- DENY por defecto; documentación en español e identificadores en inglés.
- Commits sin `Co-Authored-By` y PR sin atribución a herramientas.
