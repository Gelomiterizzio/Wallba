# Stack y decisiones

Estado: decisión de planificación, pendiente de aprobación del plan. Propietario P1; P2 revisa seguridad, P3 integración y P4 experiencia.

| Capa | Selección compatible | Alternativa y motivo de no elegirla en MVP |
|---|---|---|
| Runtime backend | Python 3.12.x | 3.13/3.14 añaden una matriz que no aporta al alcance inicial |
| HTTP y contratos | FastAPI, Pydantic 2.x strict, Uvicorn un worker | Django incluye capacidades innecesarias; Express duplicaría tipado del motor Python |
| Persistencia | SQLAlchemy 2.0.x + Alembic + SQLite | PostgreSQL cuando haya varios workers, despliegue compartido o contención real |
| Frontend | React 19.x + TypeScript 5.x + Vite compatible con Node 22.12+ | Next.js añade servidor/SSR sin necesidad de SEO en un dashboard privado |
| Estilos | Tailwind CSS 4.x, CSS tokens, primitivas accesibles Radix | Una biblioteca visual completa dificulta personalización y aumenta superficie |
| Estado | React Router + TanStack Query; estado local de formularios | Redux global no es necesario para recursos de API |
| Políticas | YAML con safe loader y JSON; Pydantic discriminated unions | OPA/Cedar son vías futuras; un DSL pequeño y cerrado basta para cuatro herramientas |
| Agente | ScriptedAgent determinista, protocolo AgentAdapter | Framework multiagente añadiría decisiones no necesarias para comprobar permisos |
| Pruebas | pytest/httpx/Hypothesis; Vitest/Testing Library/MSW; Playwright/axe | No sustituir pruebas de ejecutor por mocks end-to-end |
| Infraestructura | Docker Compose; GitHub Actions propuesto | Kubernetes, Kafka y Redis fuera del MVP |

Las familias anteriores son objetivos compatibles, no una afirmación de que ya se resolvieron instalaciones. P1 fijará patches backend en `backend/uv.lock` y P4 los frontend en `frontend/package-lock.json`; P1 coordina build/test de ambos y registra versiones e imagen digest. Evitar `latest`; dependencias nuevas requieren motivo y revisión de propietario. Renovar locks mediante PR y repetir contratos/seguridad.

## Fuentes primarias consultadas

- [FastAPI](https://fastapi.tiangolo.com/): API tipada y generación de OpenAPI.
- [Pydantic strict mode](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/): validación estricta para evitar coerciones inesperadas.
- [SQLAlchemy SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html): restricciones y tratamiento transaccional del dialecto.
- [Versiones de React](https://react.dev/versions): familia 19.
- [Vite](https://vite.dev/guide/): requisitos del runtime Node.
- [Tailwind con Vite](https://tailwindcss.com/docs/installation/using-vite): integración oficial.
- [Redes Compose](https://docs.docker.com/compose/how-tos/networking/): redes separadas para servicios.

Consultadas el 31/10/2026. La selección es una evaluación de ingeniería del equipo, no una recomendación literal de esas fuentes. Revalidar compatibilidad al resolver los locks.

## Presupuestos de rendimiento iniciales

Medir en hardware registrado y dataset de 10.000 eventos. Objetivos, todavía no resultados: evaluación p95 menor de 20 ms con 100 reglas; API de listado p95 menor de 300 ms local con página de 50; primera vista usable menor de 2 s con assets locales. Registrar distribución y fallos, sin prometer cifras para un host desconocido. Máximo 1 demo concurrente y 5 tool calls por run; 100 reglas por política; payload de 64 KiB; timeout de ejecución 10 s.

[Arquitectura](ARCHITECTURE.md) · [Índice](../README.md)
