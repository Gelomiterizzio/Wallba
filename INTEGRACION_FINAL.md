# Integración final — rama local

Repositorio: https://github.com/Gelomiterizzio/Wallba.git

`docs/TRASPASO_INTEGRACION.md` no está en el checkout ni en el historial de Git. Este informe usa el estado real de la rama `integration/final-four-contributors`, no un traspaso ausente.

## Estado de Git observado

La rama local parte de `origin/main` (`ffcc426`, merge del PR #6) y tiene dos commits que no están en `main`:

- `5cba390` — `fix(person-3): install auth dependency and start integrated API` (estaba en `feature/person-3-complete` y no en `main`)
- `fa7df1b` — `test(e2e): name the elements that cause horizontal overflow` (estaba en `feature/person-4-dashboard` y no en `main`)

No se hizo push ni se abrió un pull request.

## Pull requests ya fusionados en main

| PR | Rama | Estado | Autor |
|---|---|---|---|
| #1 y #2 | `feature/person-1-foundation` | MERGED | alexosinaga00 |
| #4 | `feature/person-1-foundation` | MERGED | alexosinaga00 |
| #3 | `feature/person-2-policies` | MERGED | Gelomiterizzio |
| #5 | `feature/person-3-complete` | MERGED | Gelomiterizzio |
| #6 | `feature/person-4-dashboard` | MERGED | alexosinaga00 |

Persona 1 entrega contratos, ejecutor sintético, agente guionado, runner e infraestructura. Persona 2 entrega el motor de políticas. Persona 3 entrega autenticación, gateway y aprobaciones. Persona 4 entrega auditoría, shell y pantallas. Esas cuatro partes ya están en `main`. Esta rama añade los dos commits posteriores y el trabajo local sin confirmar.

## Pruebas ejecutadas en esta sesión

- `tests/infra/test_live_isolation.py::test_api_runs_without_ports_of_others_failing_closed`: 1 passed en 82.99 s. Una sesión ausente y una cookie falsificada reciben 401 `AUTHENTICATION_REQUIRED` y el cuerpo no incluye `items`.
- `tests/policy/test_activation.py` y `tests/policy/test_api.py`: 13 passed.
- `tests/guard`: 19 passed, 1 skipped. El salto es la prueba de enlace simbólico: Windows no permitió crearlo.
- Vitest `src/app/app.test.tsx` y `src/features/dashboard/dashboard.test.tsx`: 21 passed.

## Recorrido del stack Compose

Proyecto desechable `wallba-review`, perfiles `demo` y `web`, publicado solo en `127.0.0.1:8080`. El contenedor `agent` termina con código 0 porque su comando es `--help`; no es un servicio permanente. `api` y `web` quedaron en ejecución.

Con la imagen construida al principio, `GET /api/v1/dashboard` respondía 404: la factory de Persona 3 no montaba el router de observabilidad. El código local ya lo monta y, tras reconstruir solo `api`, el dashboard mostró ceros reales y el texto «Sin actividad en este periodo».

Después se ejecutó el escenario S04, semilla 7, run `019970d3-4401-4f39-bc70-0a5e632ef43c`:

- Lado sin firewall: una ejecución con 1 efecto.
- Lado con firewall: decisión denegada, riesgo alto, motivo `POLICY_MISSING`, sin recibo de ejecución.

No había una política activa. La denegación es por política ausente, no por la regla `deny-delete`.

La auditoría en `/audit`, con y sin el `run_id`, mostró «Aún no hay eventos registrados» y «Ningún evento coincide con los filtros». La comparación del run sí mostró la decisión. Esas dos pantallas no están leyendo el mismo registro en este arranque.

`/approvals` en la imagen web que estaba sirviendo decía «Centro de aprobaciones aún no integrado» y «No se puede aprobar nada desde aquí». El fuente local ya monta `ApprovalCenter`, pero esa imagen no se reconstruyó. No se aprobó ninguna solicitud.

## CI de main

El run `41233355425` del merge del PR #6 tiene el job `frontend` en fallo. El mensaje es desborde horizontal en la auditoría a 1440 px. El commit `fa7df1b` no corrige el diseño: mantiene la aserción y añade el nombre de los elementos. En el fuente local, `.dialog` dejó de usar `100vw` y la tabla de filtros se limita al ancho del contenedor. Ese cambio no se volvió a ejecutar en el job de Linux.

## Activación de políticas

`policy_activation` se actualizaba si el número de versión coincidía, aunque el `policy_id` fuera otro. `other-policy` v1 podía reemplazar a `demo-policy` v1 con `expected_active_version=1`. Ahora el `UPDATE` exige `policy_id` y versión de la fila activa. Sustituir otra política exige `expected_active_policy_id` igual a la política activa. La prueba `test_version_number_does_not_identify_another_policy` cubre el rechazo y el reemplazo explícito.

## Guardia de archivos

El paquete `backend/wallba/guard` clasifica por nombre y ruta, no lee el contenido para clasificar, y guarda el estado fuera del proyecto. El hook y el shim pueden denegar antes de leer o escribir cuando la política es `block_read`, `block_write` o `block_all`. `monitor` y `alert` permiten la operación y no se presentan como bloqueo. Un cambio visto por el monitor queda como `detected`, con origen `ORIGEN NO DETERMINADO`, y el archivo no se restaura.

El snippet del hook se imprime; no se escribe en la configuración de Claude Code ni de otras herramientas.

Hay pantallas locales `/protection` y `/alerts`, un resumen en el dashboard y tema claro. La imagen web de `wallba-review` no las incluye.

## Demo verificada después del arreglo

Con `demo-policy` v1 activa y los eventos del gateway copiados a `audit_events`:

- S04, semilla 7, run `5fe195bb-e9ff-482b-a0f2-17557a999a06`: baseline con 1 efecto; lado protegido `DENY` / `RULE_DENY` / riesgo alto. La auditoría de ese run devolvió `request_received`, `authorization_decided`, `demo_started` y `demo_completed`.
- S06, run `92340e4f-36e3-4c08-8ddf-b8c2f0f2d538`: `REQUIRE_APPROVAL`. `demo-approver` aprobó `143a9bac-c879-432d-b6b2-1dec5efdbf27`. La solicitud quedó `CONSUMED` y la ejecución `SUCCEEDED` con 1 efecto.
- La imagen web reconstruida muestra «Aprobaciones humanas», Protección y Alertas.

## Límites

Un proceso con el mismo usuario puede no usar el hook o escribir la base del guardia. El monitor no demuestra lecturas ni identifica al autor. Sin política activa, el firewall de herramientas responde `POLICY_MISSING`. No se hizo revisión con lector de pantalla ni con zoom al 200 %. Los estados de `docs/planning/person-*-tasks.json` siguen en «Pendiente»; no se marcaron como hechos sin revisar cada tarea.
