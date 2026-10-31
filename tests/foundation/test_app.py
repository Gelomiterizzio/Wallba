"""App factory, salud y fallo cerrado sin puertos ajenos (WAL-P1-002)."""

from __future__ import annotations

from pathlib import Path

from conftest import LOOPBACK, VIEWER
from fastapi.testclient import TestClient

from wallba.demo.environments import HttpEnvironment
from wallba.foundation.app import create_app
from wallba.foundation.config import Settings


class _Unreachable:
    def request(self, *args, **kwargs):
        import httpx

        raise httpx.ConnectError("sin red")


def _bare_app(tmp_path: Path):
    settings = Settings(
        role="control",
        environment_id="protected-fixture",
        data_dir=tmp_path,
        executor_url="http://executor",
        executor_token="t" * 32,
    )
    return create_app(settings, protected_env=HttpEnvironment("http://executor", "t", client=_Unreachable()))


def test_import_and_factory_do_not_create_database(tmp_path: Path) -> None:
    _bare_app(tmp_path)
    assert not (tmp_path / "control.sqlite").exists()


def test_live_is_loopback_only(tmp_path: Path) -> None:
    with TestClient(_bare_app(tmp_path), client=LOOPBACK) as client:
        assert client.get("/api/v1/health/live").json() == {"status": "ok"}
    with TestClient(_bare_app(tmp_path), client=("10.0.0.5", 1234)) as client:
        assert client.get("/api/v1/health/live").status_code == 404


def test_ready_reports_missing_dependencies_with_503(tmp_path: Path) -> None:
    with TestClient(_bare_app(tmp_path), client=LOOPBACK) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"database": True, "policy": False, "executor": False}


def test_routes_fail_closed_without_authorizer(tmp_path: Path) -> None:
    with TestClient(_bare_app(tmp_path), client=LOOPBACK) as client:
        response = client.get("/api/v1/agents", headers=VIEWER)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTHORIZATION_UNAVAILABLE"


def test_errors_use_common_format_without_internal_details(lab) -> None:
    response = lab.client.get("/api/v1/no-existe")
    assert response.status_code == 404
    assert set(response.json()["error"]) == {"code", "message", "request_id", "details"}


def test_payload_limit_returns_413(lab) -> None:
    response = lab.client.post(
        "/api/v1/demo-runs", content=b"x" * (64 * 1024 + 1), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


def test_no_firewall_bypass_parameter_exists(lab) -> None:
    schema = lab.client.get("/openapi.json").json()
    assert "firewall" not in str(schema).lower().replace("wallba", "")
