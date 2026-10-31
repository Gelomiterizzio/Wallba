"""Persona 3 assembly of existing P1/P2 services; teammates' files stay untouched.

Run the SAME control-plane API using this factory to install Persona 3 ports.
There is no parallel server, embedded executor or alternate authorization path.
"""

from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from wallba.approvals.routes import build_router as approval_router
from wallba.approvals.service import ApprovalService
from wallba.auth.clock import SystemClock
from wallba.auth.http_handlers import build_fastapi_router
from wallba.auth.integration import HumanAuthorizer, create_auth
from wallba.auth.service import AuthSettings
from wallba.foundation.app import create_app as create_foundation_app
from wallba.foundation.config import load_settings
from wallba.foundation.database import create_sqlite_engine, run_migrations
from wallba.foundation.http import Integrations
from wallba.gateway.audit import TransactionalOutbox
from wallba.gateway.capability import CapabilityIssuer
from wallba.gateway.executor_client import HttpExecutorClient
from wallba.gateway.harness import Person3Harness
from wallba.gateway.routes import build_router
from wallba.gateway.service import GatewayService
from wallba.policy.repository import SqlitePolicyRepository
from wallba.policy.routes import PolicyActor, PolicyHttpError, create_policy_router
from wallba.policy.service import PolicyService

_request_context = ContextVar("person3_request", default=None)


def create_app(
    settings,
    *,
    executor=None,
    audit=None,
    clock=None,
    protected_env=None,
    baseline_env=None,
):
    settings.control_db_path.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(settings.control_db_path)
    engine = create_sqlite_engine(settings.control_db_path)
    policy_repository = SqlitePolicyRepository(settings.control_db_path)
    clock = clock or SystemClock()
    audit = audit or TransactionalOutbox()
    if settings.capability_secret is None or settings.capability_key_id is None:
        raise ValueError("P3 requiere clave de capacidad y key_id")
    executor = executor or HttpExecutorClient(
        settings.executor_url, settings.executor_token
    )
    auth = create_auth(
        engine,
        AuthSettings(
            frozenset({settings.allowed_origin}),
            "wallba_session",
            settings.allowed_origin.startswith("https://"),
        ),
        clock=clock,
    )
    authorizer = HumanAuthorizer(auth)
    gateway = GatewayService(
        engine,
        executor,
        CapabilityIssuer(settings.capability_secret, settings.capability_key_id),
        clock,
        audit,
        environment_id=settings.environment_id,
    )
    approvals = ApprovalService(gateway)
    policy_service = PolicyService(policy_repository, clock, audit)

    def policy_actor():
        request = _request_context.get()
        if request is None:
            return None
        mutation = request.method not in {"GET", "HEAD", "OPTIONS"}
        principal = authorizer.require(
            request, "policy_admin" if mutation else "viewer", mutation=mutation
        )
        return PolicyActor(
            principal.principal_id, principal.kind, frozenset(principal.roles), mutation
        )

    def policy_ready():
        try:
            return policy_repository.get_active_snapshot() is not None
        # Fail closed: a broken or unavailable policy store must never make the
        # control plane look ready.  The repository has several backend errors.
        except Exception:  # noqa: BLE001
            return False

    integrations = Integrations(
        authorizer=authorizer,
        gateway=gateway,
        audit=audit,
        harness=Person3Harness(gateway, approvals),
        policy_ready=policy_ready,
        extra_routers=[
            build_fastapi_router(auth),
            build_router(gateway, authorizer),
            approval_router(approvals, authorizer),
            create_policy_router(policy_service, policy_actor),
        ],
    )
    app = create_foundation_app(settings, integrations, protected_env, baseline_env)
    app.state.person3_gateway = gateway
    app.state.person3_approvals = approvals
    app.state.person3_auth = auth
    app.state.person3_engine = engine
    app.state.person3_policy = policy_service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allowed_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )

    @app.middleware("http")
    async def request_context(request, call_next):
        token = _request_context.set(request)
        try:
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            _request_context.reset(token)

    @app.exception_handler(PolicyHttpError)
    async def policy_error(_request, exc):
        from uuid import uuid4

        return JSONResponse(
            status_code=exc.status,
            content={
                "error": {
                    "code": exc.code,
                    "message": "La solicitud de política fue rechazada",
                    "request_id": exc.request_id or str(uuid4()),
                    "details": exc.details,
                }
            },
        )

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with original_lifespan(application):
                gateway.recover()
                yield
        finally:
            if hasattr(executor, "close"):
                executor.close()
            engine.dispose()

    app.router.lifespan_context = lifespan
    return app


def create_app_from_env():
    return create_app(load_settings())
