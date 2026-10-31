"""Persona 3 lab: real P1 executor + P2 policy + P3 HTTP/auth/gateway/approvals."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from wallba.auth.models import HumanRecord, Role
from wallba.auth.passwords import Argon2PasswordHasher
from wallba.contracts.fixture_ids import target_record_id
from wallba.contracts.ports import Principal
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER
from wallba.demo.environments import HttpEnvironment
from wallba.executor.app import create_executor_app
from wallba.executor.runtime import ExecutorRuntime
from wallba.foundation.config import Settings
from wallba.gateway.bootstrap import create_app
from wallba.gateway.executor_client import HttpExecutorClient

ORIGIN = "http://127.0.0.1:8080"
PASSWORD = "synthetic-person3-integration-passphrase"
SECRET = b"p3-isolated-capability-secret-00000"
TOKEN = "p3-isolated-service-token-00000000"


class Clock:
    def __init__(self):
        self.instant = datetime.now(UTC)

    def now(self):
        return self.instant


@dataclass
class Lab:
    app: object
    client: TestClient
    executor_client: TestClient
    runtime: object
    clock: object
    settings: object
    policy_data: dict

    @property
    def gateway(self):
        return self.app.state.person3_gateway

    @property
    def approvals(self):
        return self.app.state.person3_approvals

    def principal(self, name="operator"):
        roles = {
            "operator": ["viewer", "operator"],
            "approver": ["viewer", "approver"],
            "admin": ["viewer", "policy_admin"],
            "viewer": ["viewer"],
            "both": ["viewer", "operator", "approver"],
        }[name]
        return Principal(principal_id=f"p3-{name}", kind="human", roles=roles)

    def login(self, name="operator"):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": f"p3-{name}", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 200, response.text
        return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}

    def call(self, tool="email.send", **parameters):
        catalog = {
            "email.send": (
                "send",
                "mailbox:demo-outbox",
                {
                    "to": "reviewer@example.test",
                    "subject": "Persona 3",
                    "body": "Mensaje sintético",
                },
            ),
            "file.read": ("read", "file:public-guide", {"max_bytes": 1024}),
            "db.query": (
                "query",
                "query:demo-records",
                {"query_id": "count_records", "limit": 10},
            ),
            "record.delete": (
                "delete",
                "table:demo-records",
                {"record_id": target_record_id(0)},
            ),
        }
        operation, resource, defaults = catalog[tool]
        return TOOL_CALL_ADAPTER.validate_python(
            {
                "request_id": str(uuid4()),
                "agent_id": "demo-agent",
                "tool": tool,
                "operation": operation,
                "resource_id": resource,
                "parameters": {**defaults, **parameters},
            }
        )


@pytest.fixture
def p3_lab(tmp_path):
    protected = ExecutorRuntime(tmp_path / "protected/sandboxes", "executor")
    baseline = ExecutorRuntime(tmp_path / "baseline/sandboxes", "baseline")
    ex_settings = Settings(
        role="executor",
        environment_id="protected-fixture",
        data_dir=tmp_path / "protected",
        capability_key_id="p3-key",
        capability_secret=SECRET,
        executor_token=TOKEN,
    )
    base_settings = Settings(
        role="baseline",
        environment_id="baseline-fixture",
        data_dir=tmp_path / "baseline",
        baseline_token=TOKEN,
    )
    settings = Settings(
        role="control",
        environment_id="protected-fixture",
        data_dir=tmp_path / "control",
        capability_key_id="p3-key",
        capability_secret=SECRET,
        executor_token=TOKEN,
        demo_enabled=True,
        executor_url="http://executor",
        baseline_url="http://baseline",
        baseline_token=TOKEN,
    )
    clock = Clock()
    with (
        TestClient(create_executor_app(ex_settings, protected)) as executor_client,
        TestClient(create_executor_app(base_settings, baseline)) as baseline_client,
    ):
        executor = HttpExecutorClient("", TOKEN, client=executor_client)
        app = create_app(
            settings,
            executor=executor,
            clock=clock,
            protected_env=HttpEnvironment("", TOKEN, client=executor_client),
            baseline_env=HttpEnvironment("", TOKEN, client=baseline_client),
        )
        with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 50000)) as client:
            auth = app.state.person3_auth
            repo = auth.repository
            password_hash = Argon2PasswordHasher().hash_password(PASSWORD)
            for name, roles in {
                "operator": [Role.VIEWER, Role.OPERATOR],
                "approver": [Role.VIEWER, Role.APPROVER],
                "admin": [Role.VIEWER, Role.POLICY_ADMIN],
                "viewer": [Role.VIEWER],
                "both": [Role.VIEWER, Role.OPERATOR, Role.APPROVER],
            }.items():
                repo.add_human(
                    HumanRecord(
                        f"p3-{name}",
                        f"p3-{name}",
                        password_hash,
                        frozenset(roles),
                        False,
                    )
                )
            policy_data = json.loads(
                (Path(__file__).resolve().parents[2] / "policies/demo.json").read_text()
            )
            app.state.person3_policy.create_version(
                "demo-policy", json.dumps(policy_data).encode(), "p3-admin"
            )
            app.state.person3_policy.activate("demo-policy", 1, None, "p3-admin")
            yield Lab(
                app, client, executor_client, protected, clock, settings, policy_data
            )
    protected.sandboxes.dispose()
    baseline.sandboxes.dispose()
