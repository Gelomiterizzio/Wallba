# Persona 3 — Centro de aprobaciones

Módulo independiente de React/TypeScript, propiedad de Persona 3. Persona 4 puede integrarlo sin copiar su lógica:

```tsx
import { ApprovalCenter } from "./features/approvals"

<ApprovalCenter />
```

Consume la API real `/api/v1`. `apiBase` permite cambiar el prefijo y `client` admite un adaptador que cumpla `ApprovalApi`. No se incluyen datos inventados ni un shell paralelo al dashboard de P4. La interfaz requiere una sesión humana existente; P4 integra su navegación/login.

Incluye listado/filtros/paginación, detalle exacto y motivos obligatorios para aprobar/rechazar/cancelar. Las mutaciones no se reintentan automáticamente. Cada confirmación captura la versión que el humano revisó; 409/410 provoca lectura nueva. CSRF se obtiene de `/auth/me`, solo vive en memoria y se envía por cabecera. La cookie de sesión permanece HttpOnly.

Polling cada cinco segundos con pausa en pestañas ocultas, abort al desmontar y prevención de solicitudes de lectura superpuestas. Un resultado UNKNOWN se presenta como incertidumbre sin botón de reejecución. El backend verifica siempre identidad, rol, snapshot, vencimiento y consumo único; ocultar botones no constituye autorización.

El diálogo tiene etiquetas, foco inicial, trampa de Tab y Escape/retorno de foco. Layout responsive y CSS con prefijo `p3-approvals` para evitar colisiones. Las pruebas de DOM/cliente y typecheck se ejecutan desde `tests/approvals/ui`; no necesitan editar el package.json de P4.

Los tests usan dobles explícitos y no prueban que el dashboard completo de Persona 4 esté integrado. Esa revisión visual conjunta queda pendiente mientras P4 termina su entrega.

## Verificación ejecutada

En el harness aislado `tests/approvals/ui` se ejecutó TypeScript sin errores, 20 pruebas Vitest de DOM/cliente y tres pruebas Chromium reales a 360/768/1280 px. Las pruebas de navegador comprobaron teclado/foco, una sola mutación con versión y CSRF exactos, ausencia de overflow horizontal de página y axe completo (incluido contraste) sin violaciones en detalle y diálogo. La revisión de capturas confirmó que el contenido no se solapa a 360 px y que el diálogo mantiene los controles visibles.

La primera pasada de axe de navegador detectó un nombre accesible que no incluía el texto visible del botón de selección. Se corrigió el botón para derivar su nombre del contenido real y se repitió la verificación con éxito; no se desactivó esa regla en navegador. Las dos reglas que necesitan layout/canvas se omiten solo en jsdom y se comprueban en Chromium real.

Desde el harness:

```powershell
npm ci --registry https://registry.npmjs.org
npm run typecheck
npm test
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD '.browser-cache'
npx playwright install chromium
npm run test:browser
```

Screenshots y resultado JSON se generan bajo `.artifacts/`, con badge visible DATOS DE PRUEBA. Browser cache, node_modules y artifacts no se publican. No hubo commits ni pushes desde esta tarea.
