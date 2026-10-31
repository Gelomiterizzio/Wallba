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

El harness de `tests/approvals/ui` pasó typecheck y 21 pruebas Vitest. Las
3 pruebas Chromium pasaron a 360, 768 y 1280 px al ejecutarse con acceso a
puertos locales. La primera repetición dentro del sandbox no pudo abrir el
puerto de Vite; esto no era un fallo de la interfaz. Para repetirlas:

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
Se fijó en el manifiesto y lock compartidos para que la instalación congelada
de CI y Docker funcione. El contenedor API arranca la fábrica de Persona 3,
que incorpora la aplicación existente de Persona 1 y las políticas de Persona 2.
La instalación limpia desde `uv.lock` pasó y, en ese entorno, la suite completa
dio 334 pruebas correctas y 15 omitidas. No se pudo construir la imagen en esta
máquina porque Docker no está instalado.

Persona 4 todavía no terminó su dashboard, por lo que la integración visual
final queda bloqueada externamente. El componente de Persona 3 y sus contratos
API quedan listos, sin alterar el frontend ajeno.
