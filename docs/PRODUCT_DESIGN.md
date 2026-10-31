# Diseño de producto

No se recibieron imágenes ni referencias visuales concretas. Lo siguiente es una propuesta original para revisión, no una reproducción de material adjunto. P4 dirige sistema visual; P2 construye editor de políticas y P3 centro de aprobaciones usando las mismas primitivas.

## Tokens y comportamiento

Fondo #0B1120, superficie #111C30, borde #334155, texto primario #F1F5F9, secundario #CBD5E1, acento #22D3EE. Estados: permitido verde #4ADE80, denegado rojo #FCA5A5, pendiente ámbar #FCD34D, UNKNOWN violeta #D8B4FE. Verificar contrastes WCAG AA en las combinaciones usadas; no asumir que la paleta por sí misma satisface accesibilidad. Texto, icono y etiqueta acompañan el color.

Tipografía system-ui, monospace para IDs/digests. Tamaños 12 metadata, 14 cuerpo denso, 16 cuerpo, 24 título, 32 KPI. Espaciado base 4px: 4/8/12/16/24/32; radios 8/12; foco 2px con offset, targets al menos 44px. Transiciones 120–180ms en hover/focus/carga; `prefers-reduced-motion` desactiva desplazamientos. No animar decisiones como si fueran pruebas de ejecución.

Desktop >=1280: sidebar 240px, header 64px, contenido máx. 1440px y margen 24. Tablet 768–1279: sidebar colapsada, 2 columnas KPI. Móvil <768: navegación drawer, 1 columna; tablas con scroll horizontal y encabezado accesible, resumen de fila a tarjetas cuando sea útil. Pruebas a 360, 768, 1280, 1920px y zoom 200%.

Primitivas: AppShell, PageHeader, StatCard, DecisionBadge, RiskBadge, DataTable, FilterBar, DateRange, JsonViewer, CodeEditor accesible con fallback textarea, RequestTimeline, EvidenceLink, ConfirmDialog, EmptyState, ErrorState, Skeleton, Toast. Focus trap y retorno de foco en diálogos; teclado en todo control; live region discreta para actualización sin anunciar cada log.

## Pantallas y APIs

| Pantalla / dueño | Estructura y acciones | Datos y estados |
|---|---|---|
| Dashboard P4 | KPIs arriba, decisiones y riesgo al centro, actividad abajo; rango y environment visibles | GET /dashboard; cero real distinto de loading; as_of, stale badge y retry |
| Agentes P4 | Tabla nombre/estado/tools, drawer de detalle y scopes | GET /agents y /agents/{id}; no prometer CRUD no previsto; missing agent 404 |
| Políticas P2 | Lista versiones, editor YAML/JSON, errores por línea, diff y activar versión validada | /policies/*; solo policy_admin edita; 409 recarga activa; validar no activa |
| Aprobaciones P3 | Pendientes con expiry server; detalle snapshot, riesgo, política/digest; aprobar/rechazar con motivo | /approvals/*; no aceptar parámetros nuevos; 409/410 refresca estado, no toast de éxito falso |
| Auditoría P4 | Filtros y tabla paginada, detalle timeline y evidencia, export JSONL | /audit*; redaction, empty por filtros, límites de export visibles |
| Playground P4 | Catálogo, seed, ejecutar comparación, dos columnas antes/solicitud/decisión/efecto | /scenarios,/demo-runs/*; operator; pendiente requiere humano real, UNKNOWN explícito |
| Matriz P4 | Escenario/tool/params saneados/riesgo/política/resultado A/B/motivo/evidencia | GET /matrix P1; solo runs ejecutados; vacío inicial con CTA Playground |

Login es pantalla utilitaria P3 integrada en shell P4: error genérico sin enumerar cuentas, labels persistentes, no password demo embebido. Mostrar identidad/roles, logout y entorno `DEMO AISLADA` en header. Todos los controles visuales de permisos son una ayuda; API decide siempre.

## Especificación de estados

Loading conserva layout con skeleton y aria-busy; evita reemplazar registros por ceros. Error muestra mensaje en español, request_id y acción retry, sin contenido técnico sensible. Vacío inicial indica que aún no se ejecutaron escenarios; vacío filtrado ofrece limpiar filtros. Mutación pendiente deshabilita duplicados pero servidor mantiene idempotencia. Datos antiguos conservan timestamp y aviso. Fallo de red conserva formulario y no asume éxito. Un badge `DATOS DE EJEMPLO` persiste en todas las vistas MSW. En demo final se muestran únicamente datos API reales.

En Playground no rotular expectativa como resultado. Mostrar trace del agente y la llamada efectiva; el escenario inyectado incluye un documento sintético hostil visible como contenido citado. La comparación muestra fixture_digest igual antes de ejecutar y efectos posteriores por lado; política inválida/replay no se representan como una herramienta ejecutada. Evidencia enlaza manifest sin secretos. Exportar filas reales conserva run_id y hora.

## Criterios visuales

Navegar siete pantallas por teclado; foco visible y orden lógico; formularios con label/error asociado; contraste medido; axe sin violaciones críticas/graves; teclado manual y lector de pantalla en flujo aprobar; responsive sin solapamiento. P4 entrega screenshots con viewport/version y pruebas; P2/P3 entregan evidencia de sus pantallas. No se deben presentar estas validaciones como ejecutadas durante planificación.

[Manual P4](team/PERSON_4_MASTER_PLAN.md) · [API](API_CONTRACTS.md) · [Índice](../README.md)
