"""API interna del ejecutor. Solo accesible por la red interna y con token de servicio.

El proceso protegido expone `execute` con capacidad. Solo el baseline expone la
ruta sin capacidad: el protegido no tiene ningún flag que la active.
"""

from __future__ import annotations

import hmac
import re
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse

from wallba.contracts.api import EnvironmentView, HealthLive
from wallba.contracts.capability import ExecuteCommand
from wallba.contracts.common import UUID_PATTERN, StrictModel
from wallba.contracts.decision import ExecutionReceipt
from wallba.contracts.results import ToolResult
from wallba.contracts.tool_call import ToolCall
from wallba.executor.capabilities import CapabilityVerifier
from wallba.executor.errors import CapabilityRejected
from wallba.executor.runtime import ExecutorRuntime
from wallba.executor.sandbox import SandboxError
from wallba.executor.service import BaselineExecutor, ExecutorService
from wallba.foundation.config import ConfigError, Settings, load_settings

REJECTION_STATUS = {
    "NONCE_REPLAY": status.HTTP_409_CONFLICT,
    "STALE_RESOURCE": status.HTTP_409_CONFLICT,
    "DIGEST_MISMATCH": status.HTTP_409_CONFLICT,
}


class PrepareEnvironment(StrictModel):
    run_id: str
    seed: int


class ResourceVersionView(StrictModel):
    resource_id: str
    version: int


def _service_token(settings: Settings) -> str:
    token = settings.executor_token if settings.role == "executor" else settings.baseline_token
    if token is None:
        raise ConfigError("falta el token de servicio del ejecutor")
    return token


def create_executor_app(
    settings: Settings,
    runtime: ExecutorRuntime | None = None,
    service: ExecutorService | None = None,
) -> FastAPI:
    if settings.role not in {"executor", "baseline"}:
        raise ConfigError("create_executor_app requiere rol executor o baseline")
    token = _service_token(settings)
    runtime = runtime or ExecutorRuntime(settings.sandbox_root, settings.role)
    app = FastAPI(title="WALLBA executor", docs_url=None, redoc_url=None, openapi_url=None)

    def authenticate(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = f"Bearer {token}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="SERVICE_UNAUTHORIZED")

    guard = [Depends(authenticate)]

    @app.get("/health/live")
    def live() -> HealthLive:
        return HealthLive(status="ok")

    @app.post("/internal/environments", dependencies=guard)
    def prepare(command: PrepareEnvironment) -> EnvironmentView:
        try:
            sandbox = runtime.activate(command.run_id, command.seed)
        except SandboxError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="INVALID_RUN_ID") from exc
        return EnvironmentView(
            run_id=sandbox.run_id,
            fixture_digest=sandbox.fixture_digest,
            snapshot=sandbox.snapshot(),
        )

    @app.get("/internal/environments/{run_id}", dependencies=guard)
    def snapshot(run_id: str) -> EnvironmentView:
        try:
            sandbox = runtime.sandboxes.get(run_id)
        except SandboxError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="ENVIRONMENT_NOT_FOUND") from exc
        return EnvironmentView(
            run_id=sandbox.run_id,
            fixture_digest=sandbox.fixture_digest,
            snapshot=sandbox.snapshot(),
        )

    @app.delete("/internal/environments/{run_id}", dependencies=guard, status_code=204)
    def reset(run_id: str) -> None:
        try:
            runtime.reset(run_id)
        except SandboxError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="RESET_REJECTED") from exc

    if settings.role == "baseline":
        baseline = BaselineExecutor(runtime)

        @app.post("/internal/baseline/execute", dependencies=guard)
        def baseline_execute(call: ToolCall) -> ExecutionReceipt:
            return baseline.execute(call)

        return app

    if service is None:
        if settings.capability_secret is None or settings.capability_key_id is None:
            raise ConfigError("el ejecutor protegido requiere clave de capacidad")
        verifier = CapabilityVerifier(
            {settings.capability_key_id: settings.capability_secret}, settings.environment_id
        )
        service = ExecutorService(runtime, verifier)
    protected = service

    @app.exception_handler(CapabilityRejected)
    def rejected(_request, exc: CapabilityRejected) -> JSONResponse:
        code = REJECTION_STATUS.get(exc.code, status.HTTP_403_FORBIDDEN)
        return JSONResponse(status_code=code, content={"detail": exc.code})

    @app.post("/internal/execute", dependencies=guard)
    def execute(command: ExecuteCommand) -> ExecutionReceipt:
        return protected.execute(command.request, command.capability)

    @app.get("/internal/receipts/{execution_id}", dependencies=guard)
    def receipt(execution_id: str) -> ExecutionReceipt:
        if not re.fullmatch(UUID_PATTERN, execution_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="INVALID_EXECUTION_ID")
        found = protected.receipt(execution_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="RECEIPT_NOT_FOUND")
        return found

    @app.get("/internal/results/{execution_id}", dependencies=guard)
    def result(execution_id: str) -> ToolResult:
        found = protected.result(execution_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="RESULT_NOT_FOUND")
        return found

    @app.get("/internal/resources/{resource_id}/version", dependencies=guard)
    def resource_version(resource_id: str) -> ResourceVersionView:
        version = protected.resource_version(resource_id)
        if version is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="UNKNOWN_RESOURCE")
        return ResourceVersionView(resource_id=resource_id, version=version)

    return app


def create_app_from_env() -> FastAPI:
    """Factory de uvicorn para los procesos executor y baseline."""
    return create_executor_app(load_settings())
