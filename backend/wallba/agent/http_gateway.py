"""Cliente del gateway para el proceso agente: su único camino hacia las herramientas."""

from __future__ import annotations

import httpx

from wallba.contracts.decision import RequestView
from wallba.contracts.ports import Principal
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER, ToolCall

REQUEST_TIMEOUT_SECONDS = 10.0


class GatewayRejected(Exception):
    """El gateway rechazó la solicitud (401, 403, 409, 422, 503...)."""

    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(f"{status_code} {code}")
        self.status_code = status_code
        self.code = code


class HttpToolGateway:
    def __init__(self, api_url: str, bearer: str, client: httpx.Client | None = None) -> None:
        self._base = api_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {bearer}"}
        self._client = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)

    def submit(self, call: ToolCall, _principal: Principal | None, idempotency_key: str) -> RequestView:
        response = self._client.post(
            f"{self._base}/api/v1/tool-requests",
            content=TOOL_CALL_ADAPTER.dump_json(call),
            headers={
                **self._headers,
                "Idempotency-Key": idempotency_key,
                "Content-Type": "application/json",
            },
        )
        return self._parse(response)

    def get(self, request_id: str, _principal: Principal | None) -> RequestView:
        response = self._client.get(
            f"{self._base}/api/v1/tool-requests/{request_id}", headers=self._headers
        )
        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> RequestView:
        if response.status_code in {200, 202}:
            return RequestView.model_validate_json(response.content)
        try:
            code = response.json()["error"]["code"]
        except (ValueError, KeyError, TypeError):
            code = "UNEXPECTED_RESPONSE"
        raise GatewayRejected(response.status_code, code)
