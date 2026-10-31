"""Cliente interno hacia los procesos ejecutores protegido y baseline."""

from __future__ import annotations

import httpx

from wallba.contracts.api import EnvironmentView, ResourceSnapshot
from wallba.contracts.decision import ExecutionReceipt
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER, ToolCall

EXECUTION_TIMEOUT_SECONDS = 10.0


class ExecutorUnavailable(Exception):
    """Sin respuesta del ejecutor: el resultado de un efecto queda incierto."""


class HttpEnvironment:
    def __init__(self, base_url: str, token: str, client: httpx.Client | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._client = client or httpx.Client(timeout=EXECUTION_TIMEOUT_SECONDS)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self._client.request(method, f"{self._base}{path}", headers=self._headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ExecutorUnavailable(path) from exc

    def prepare(self, run_id: str, seed: int) -> EnvironmentView:
        response = self._request("POST", "/internal/environments", json={"run_id": run_id, "seed": seed})
        response.raise_for_status()
        return EnvironmentView.model_validate_json(response.content)

    def snapshot(self, run_id: str) -> ResourceSnapshot:
        response = self._request("GET", f"/internal/environments/{run_id}")
        response.raise_for_status()
        return EnvironmentView.model_validate_json(response.content).snapshot

    def reset(self, run_id: str) -> None:
        self._request("DELETE", f"/internal/environments/{run_id}").raise_for_status()

    def receipt(self, execution_id: str) -> ExecutionReceipt | None:
        response = self._request("GET", f"/internal/receipts/{execution_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return ExecutionReceipt.model_validate_json(response.content)

    def execute_unsafe(self, call: ToolCall) -> ExecutionReceipt:
        """Solo existe en el proceso baseline; el protegido responde 404."""
        response = self._request(
            "POST",
            "/internal/baseline/execute",
            json=TOOL_CALL_ADAPTER.dump_python(call, mode="json"),
        )
        response.raise_for_status()
        return ExecutionReceipt.model_validate_json(response.content)

    def is_live(self) -> bool:
        try:
            return self._request("GET", "/health/live").status_code == 200
        except ExecutorUnavailable:
            return False
