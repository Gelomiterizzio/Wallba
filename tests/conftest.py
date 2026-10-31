"""Fixtures compartidas de las pruebas de P1. Todo vive en directorios temporales."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from support.fakes import (
    BASELINE_TOKEN,
    CAPABILITY_SECRET,
    ENVIRONMENT_ID,
    EXECUTOR_TOKEN,
    KEY_ID,
    FakeAuditSink,
    FakeAuthorizer,
    FakeGateway,
    FakeHarness,
)

from wallba.demo.environments import HttpEnvironment
from wallba.executor.app import create_executor_app
from wallba.executor.capabilities import CapabilityVerifier
from wallba.executor.runtime import ExecutorRuntime
from wallba.executor.service import ExecutorService
from wallba.foundation.app import create_app
from wallba.foundation.config import Settings
from wallba.foundation.http import Integrations

LOOPBACK = ("127.0.0.1", 50000)


@pytest.fixture
def runtime(tmp_path: Path) -> Iterator[ExecutorRuntime]:
    value = ExecutorRuntime(tmp_path / "sandboxes", "executor")
    yield value
    value.sandboxes.dispose()


@pytest.fixture
def service(runtime: ExecutorRuntime) -> ExecutorService:
    verifier = CapabilityVerifier({KEY_ID: CAPABILITY_SECRET}, ENVIRONMENT_ID)
    return ExecutorService(runtime, verifier)


def executor_settings(data_dir: Path) -> Settings:
    return Settings(
        role="executor",
        environment_id=ENVIRONMENT_ID,
        data_dir=data_dir,
        capability_key_id=KEY_ID,
        capability_secret=CAPABILITY_SECRET,
        executor_token=EXECUTOR_TOKEN,
    )


def baseline_settings(data_dir: Path) -> Settings:
    return Settings(
        role="baseline",
        environment_id="baseline-fixture",
        data_dir=data_dir,
        baseline_token=BASELINE_TOKEN,
    )


@dataclass
class Lab:
    client: TestClient
    gateway: FakeGateway
    audit: FakeAuditSink
    harness: FakeHarness | None
    integrations: Integrations
    executor_client: TestClient
    baseline_client: TestClient


def _build_lab(tmp_path: Path, *, with_harness: bool = False) -> Iterator[Lab]:
    protected_runtime = ExecutorRuntime(tmp_path / "protected" / "sandboxes", "executor")
    baseline_runtime = ExecutorRuntime(tmp_path / "baseline" / "sandboxes", "baseline")
    executor_app = create_executor_app(executor_settings(tmp_path / "protected"), protected_runtime)
    baseline_app = create_executor_app(baseline_settings(tmp_path / "baseline"), baseline_runtime)
    with TestClient(executor_app) as executor_client, TestClient(baseline_app) as baseline_client:
        gateway = FakeGateway(executor_client)
        audit = FakeAuditSink()
        harness = FakeHarness() if with_harness else None
        integrations = Integrations(
            authorizer=FakeAuthorizer(), gateway=gateway, audit=audit, harness=harness
        )
        settings = Settings(
            role="control",
            environment_id=ENVIRONMENT_ID,
            demo_enabled=True,
            data_dir=tmp_path / "control",
            capability_key_id=KEY_ID,
            capability_secret=CAPABILITY_SECRET,
            executor_url="http://executor",
            baseline_url="http://baseline",
            executor_token=EXECUTOR_TOKEN,
            baseline_token=BASELINE_TOKEN,
        )
        app = create_app(
            settings,
            integrations,
            protected_env=HttpEnvironment("", EXECUTOR_TOKEN, client=executor_client),
            baseline_env=HttpEnvironment("", BASELINE_TOKEN, client=baseline_client),
        )
        with TestClient(app, client=LOOPBACK) as client:
            yield Lab(client, gateway, audit, harness, integrations, executor_client, baseline_client)
    protected_runtime.sandboxes.dispose()
    baseline_runtime.sandboxes.dispose()


@pytest.fixture
def lab(tmp_path: Path) -> Iterator[Lab]:
    yield from _build_lab(tmp_path)


@pytest.fixture
def lab_with_harness(tmp_path: Path) -> Iterator[Lab]:
    yield from _build_lab(tmp_path, with_harness=True)


VIEWER = {"x-test-role": "viewer"}
OPERATOR = {"x-test-role": "operator", "x-csrf-token": "test-csrf"}
