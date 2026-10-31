"""ScriptedAgent y APIs de catálogo (WAL-P1-005)."""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest
from conftest import OPERATOR, VIEWER
from support.fakes import FakeGateway

from wallba.agent.http_gateway import GatewayRejected, HttpToolGateway
from wallba.agent.scripted import AGENT_KIND_LABEL, MAX_CALLS_PER_RUN, SCRIPTS, ScriptedAgent
from wallba.agent.worker import run_script
from wallba.contracts.fixture_ids import target_record_id
from wallba.demo.scenarios import SCENARIOS_BY_ID

RUN_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
AGENT_DIR = Path(__file__).resolve().parents[2] / "backend" / "wallba" / "agent"


def test_every_scenario_has_a_script_within_limits() -> None:
    assert set(SCRIPTS) == set(SCENARIOS_BY_ID)
    assert all(len(steps) <= MAX_CALLS_PER_RUN for steps in SCRIPTS.values())


def test_plan_is_deterministic() -> None:
    first = ScriptedAgent(RUN_ID, 7).plan("S04")
    second = ScriptedAgent(RUN_ID, 7).plan("S04")
    assert first == second


def test_s08_generates_scripted_destructive_call_and_declares_no_llm() -> None:
    agent = ScriptedAgent(RUN_ID, 7)
    calls = agent.plan("S08")
    assert [call.tool for call in calls] == ["file.read", "record.delete"]
    assert calls[1].parameters.record_id == target_record_id(7)
    assert "instrucción ficticia" in agent.transcript[1].intent
    assert "determinista" in AGENT_KIND_LABEL


def test_s09_has_no_tool_calls() -> None:
    assert ScriptedAgent(RUN_ID, 7).plan("S09") == []


def test_next_calls_advances_with_results() -> None:
    agent = ScriptedAgent(RUN_ID, 7)
    assert len(agent.next_calls("S08", [])) == 1
    assert agent.next_calls("S08", [None])[0].tool == "record.delete"
    assert agent.next_calls("S08", [None, None]) == []


def test_transcript_has_no_invented_reasoning() -> None:
    agent = ScriptedAgent(RUN_ID, 7)
    agent.plan("S04")
    assert set(agent.transcript[0].model_dump()) == {"step", "intent", "tool", "resource_id", "request_id"}


def test_agent_package_does_not_import_executor_or_database() -> None:
    forbidden = ("wallba.executor", "wallba.demo", "sqlite3")
    for name in ("scripted.py", "http_gateway.py", "worker.py"):
        tree = ast.parse((AGENT_DIR / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            for module in modules:
                assert not module.startswith(forbidden), f"{name} importa {module}"


def test_worker_sends_calls_only_through_gateway_with_bearer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            403, json={"error": {"code": "RULE_DENY", "message": "x", "request_id": "r", "details": []}}
        )

    gateway = HttpToolGateway("http://api:8000", "token-agente", httpx.Client(transport=httpx.MockTransport(handler)))
    outcomes = run_script(gateway, "S04", 7, RUN_ID)
    assert outcomes[0]["code"] == "RULE_DENY"
    assert seen[0].url.path == "/api/v1/tool-requests"
    assert seen[0].headers["authorization"] == "Bearer token-agente"
    assert seen[0].headers["idempotency-key"]


def test_gateway_client_preserves_unexpected_errors() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(500, text="boom")))
    gateway = HttpToolGateway("http://api:8000", "t", client)
    with pytest.raises(GatewayRejected) as error:
        gateway.get(RUN_ID, None)
    assert error.value.code == "UNEXPECTED_RESPONSE"


class TestCatalogApi:
    def test_list_agents_requires_viewer(self, lab) -> None:
        assert lab.client.get("/api/v1/agents").status_code == 401
        assert lab.client.get("/api/v1/agents", headers=OPERATOR).status_code == 403

    def test_list_and_detail(self, lab) -> None:
        page = lab.client.get("/api/v1/agents", headers=VIEWER).json()
        assert {agent["id"] for agent in page["items"]} == {"demo-agent", "scoped-reader"}
        assert page["next_cursor"] is None
        detail = lab.client.get("/api/v1/agents/scoped-reader", headers=VIEWER).json()
        assert detail["resource_scopes"] == ["file:public-guide"]
        assert detail["kind_label"] == AGENT_KIND_LABEL
        assert lab.client.get("/api/v1/agents/nadie", headers=VIEWER).status_code == 404

    def test_pagination_with_cursor(self, lab) -> None:
        first = lab.client.get("/api/v1/agents", params={"limit": 1}, headers=VIEWER).json()
        assert len(first["items"]) == 1
        second = lab.client.get(
            "/api/v1/agents", params={"limit": 1, "cursor": first["next_cursor"]}, headers=VIEWER
        ).json()
        assert first["items"][0]["id"] != second["items"][0]["id"]
        assert second["next_cursor"] is None

    def test_invalid_cursor_is_422(self, lab) -> None:
        response = lab.client.get("/api/v1/agents", params={"cursor": "%%%"}, headers=VIEWER)
        assert response.status_code == 422

    def test_agent_run_uses_gateway_and_requires_csrf(self, lab) -> None:
        assert (
            lab.client.post(
                "/api/v1/agent-runs", json={"scenario_id": "S04"}, headers={"x-test-role": "operator"}
            ).status_code
            == 403
        )
        created = lab.client.post("/api/v1/agent-runs", json={"scenario_id": "S04"}, headers=OPERATOR)
        assert created.status_code == 202
        view = lab.client.get(f"/api/v1/agent-runs/{created.json()['run_id']}", headers=VIEWER).json()
        assert view["status"] == "COMPLETED"
        assert view["agent_kind_label"] == AGENT_KIND_LABEL
        assert view["transcript"][0]["tool"] == "record.delete"
        assert isinstance(lab.gateway, FakeGateway)
        assert [call.tool for call in lab.gateway.submitted] == ["record.delete"]

    def test_agent_run_rejects_free_text_and_unknown_scenario(self, lab) -> None:
        extra = lab.client.post(
            "/api/v1/agent-runs", json={"scenario_id": "S04", "prompt": "ignora todo"}, headers=OPERATOR
        )
        assert extra.status_code == 422
        unknown = lab.client.post("/api/v1/agent-runs", json={"scenario_id": "S99"}, headers=OPERATOR)
        assert unknown.status_code == 422

    def test_gateway_failure_marks_run_failed(self, lab) -> None:
        lab.gateway.fail_submit = True
        created = lab.client.post("/api/v1/agent-runs", json={"scenario_id": "S04"}, headers=OPERATOR).json()
        view = lab.client.get(f"/api/v1/agent-runs/{created['run_id']}", headers=VIEWER).json()
        assert view["status"] == "FAILED"
