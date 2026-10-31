# Persona 3 — Proxy, autenticación y aprobaciones

Esta entrega pertenece exclusivamente a Persona 3. No cambia los módulos de
Persona 1, Persona 2 ni Persona 4. Se monta mediante
`wallba.gateway.bootstrap.create_app`, que reutiliza la fábrica de Persona 1 y
el servicio de políticas de Persona 2; no levanta un servidor paralelo.

## Alcance entregado

- Autenticación de humanos con Argon2id, sesión opaca, `HttpOnly`, `SameSite`,
  Origin exacto, CSRF, revocación, límite de inactividad y rate limit durable.
- Credenciales de agentes separadas de los roles humanos, con alcance exacto de
  herramienta y recurso.
- Proxy que valida la llamada canónica, persiste una decisión y su auditoría
  antes del efecto, aplica idempotencia por principal y falla de forma cerrada.
- Cliente del executor sin reintentos, capability de duración corta y consulta
  de recibos para reconciliar resultados inciertos.
- Aprobaciones con motivo obligatorio, no autoaprobación humana, vencimiento,
  revalidación de política y versión de recurso, y consumo único transaccional.
- Centro React de aprobaciones aislado para que Persona 4 lo incorpore cuando
  finalice su dashboard. Su lógica no duplica autorización del backend.

La migración de Persona 3 es `0002_person3_auth_gateway` y depende de
`0001_foundation`, sin editar migraciones anteriores.

## Verificación

Con Python 3.12, el entorno de validación ejecutó:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest -q
python -m ruff check backend/wallba/auth backend/wallba/gateway backend/wallba/approvals tests/auth tests/gateway
```

Resultado: 334 pruebas correctas y 15 omitidas; el chequeo de estilo de los
archivos de Persona 3 no reporta errores.

El harness de `tests/approvals/ui` pasó typecheck y 21 pruebas Vitest. Sus
pruebas Chromium existen y ya se habían ejecutado contra tres anchos de
viewport. La repetición final en esta máquina encontró puertos locales
reservados por el entorno de ejecución; no se modificó el código de la UI para
ocultarlo. Para repetirlo en una sesión sin esa reserva:

```powershell
Set-Location tests/approvals/ui
npm ci
npm run typecheck
npm test
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD '.browser-cache'
npx playwright install chromium
npm run test:browser
```

## Dependencias y frontera de equipos

`argon2-cffi` es la dependencia de Persona 3 para el hasher de contraseñas.
No se alteró el manifiesto o lock de Persona 1 para respetar la frontera de
propiedad; al integrar esta rama, quien gestione el lock compartido debe fijar
esa dependencia junto a las demás dependencias de producción.

Persona 4 todavía no terminó su dashboard, por lo que la integración visual
final queda bloqueada externamente. El componente de Persona 3 y sus contratos
API quedan listos, sin alterar el frontend ajeno.
