"""App factory de la API de control. No abre conexiones durante el import."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from wallba.agent.routes import router as agent_router
from wallba.agent.service import seed_agents
from wallba.contracts.api import HealthLive, HealthReady
from wallba.demo.environments import HttpEnvironment
from wallba.demo.routes import router as demo_router
from wallba.demo.runner import PairedRunner
from wallba.foundation.config import ConfigError, Settings, load_settings
from wallba.foundation.database import create_sqlite_engine, run_migrations
from wallba.foundation.http import (
    ApiError,
    Integrations,
    install_error_handlers,
    install_payload_limit,
)

API_PREFIX = "/api/v1"
LOOPBACK_HOSTS = {"127.0.0.1", "::1"}


def _require_loopback(request: Request) -> None:
    client = request.client
    if client is None or client.host not in LOOPBACK_HOSTS:
        raise ApiError(404, "NOT_FOUND", "Recurso no encontrado")


def _database_ready(app: FastAPI) -> bool:
    try:
        with app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - readiness: cualquier fallo significa no listo
        return False


def _policy_ready(integrations: Integrations) -> bool:
    probe = integrations.policy_ready
    if probe is None:
        return False
    try:
        return bool(probe())
    except Exception:  # noqa: BLE001 - un motor que falla no está listo
        return False


def create_app(
    settings: Settings,
    integrations: Integrations | None = None,
    protected_env: HttpEnvironment | None = None,
    baseline_env: HttpEnvironment | None = None,
) -> FastAPI:
    if settings.role != "control":
        raise ConfigError("create_app requiere rol control")
    integrations = integrations or Integrations()
    if protected_env is None:
        protected_env = HttpEnvironment(settings.executor_url, settings.executor_token)
    if baseline_env is None and settings.demo_enabled:
        baseline_env = HttpEnvironment(settings.baseline_url, settings.baseline_token)

    def build_runner(current: Integrations) -> PairedRunner | None:
        if current.gateway is None or current.audit is None or baseline_env is None:
            return None
        return PairedRunner(
            app.state.engine,
            current.gateway,
            current.audit,
            baseline_env,
            protected_env,
            harness=current.harness,
        )

    @asynccontextmanager
    async def lifespan(app_: FastAPI) -> AsyncIterator[None]:
        run_migrations(settings.control_db_path)
        app_.state.engine = create_sqlite_engine(settings.control_db_path)
        seed_agents(app_.state.engine)
        runner = build_runner(integrations)
        if runner is not None:
            runner.recover_interrupted()
        yield
        app_.state.engine.dispose()

    app = FastAPI(title="WALLBA API", version="1", lifespan=lifespan)
    app.state.settings = settings
    app.state.integrations = integrations
    app.state.runner_factory = build_runner
    install_error_handlers(app)
    install_payload_limit(app)

    app.include_router(agent_router, prefix=API_PREFIX)
    app.include_router(demo_router, prefix=API_PREFIX)
    # Los dueños de policy/auth/gateway/approvals/observability registran aquí sus routers.
    for router in integrations.extra_routers:
        app.include_router(router, prefix=API_PREFIX)

    @app.get(f"{API_PREFIX}/health/live")
    def live(request: Request) -> HealthLive:
        _require_loopback(request)
        return HealthLive(status="ok")

    @app.get(f"{API_PREFIX}/health/ready", response_model=HealthReady)
    def ready(request: Request) -> JSONResponse:
        _require_loopback(request)
        result = HealthReady(
            database=_database_ready(app),
            policy=_policy_ready(integrations),
            executor=protected_env.is_live(),
        )
        all_ready = result.database and result.policy and result.executor
        return JSONResponse(status_code=200 if all_ready else 503, content=result.model_dump())

    return app


def control_integrations(settings: Settings) -> Integrations:
    """Puertos ya disponibles. Sin autorizador ni gateway de P3, sus rutas responden 503."""
    # Imports locales: la imagen del ejecutor no incluye estos módulos.
    from wallba.observability.router import router as observability_router
    from wallba.observability.writer import AuditWriter
    from wallba.policy.repository import SqlitePolicyRepository

    def policy_ready() -> bool:
        return SqlitePolicyRepository(settings.control_db_path).get_active_snapshot() is not None

    return Integrations(
        audit=AuditWriter(),
        policy_ready=policy_ready,
        extra_routers=[observability_router],
    )


def create_app_from_env() -> FastAPI:
    """Factory de uvicorn."""
    settings = load_settings()
    return create_app(settings, control_integrations(settings))
