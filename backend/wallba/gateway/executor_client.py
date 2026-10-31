"""P3 client of the existing P1 executor. Never retries an execution."""

from threading import Lock
from urllib.parse import quote

import httpx

from wallba.contracts.decision import ExecutionReceipt


class ExecutorRejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class ExecutionUncertain(Exception):
    pass


class HttpExecutorClient:
    def __init__(self, base_url, token, *, client=None):
        self._client = client or httpx.Client(
            base_url=base_url, timeout=10, follow_redirects=False
        )
        self._headers = {"Authorization": f"Bearer {token}"}
        self._owned = client is None
        self._metadata_lock = Lock()

    def execute(self, canonical_request, capability):
        try:
            response = self._client.post(
                "/internal/execute",
                json={
                    "request": canonical_request.model_dump(mode="json"),
                    "capability": capability.model_dump(mode="json"),
                },
                headers=self._headers,
            )
            if response.status_code in {400, 401, 403, 404, 409, 422}:
                try:
                    code = response.json().get("detail")
                except ValueError:
                    code = None
                safe = (
                    code
                    if code in {"STALE_RESOURCE", "NONCE_REPLAY", "DIGEST_MISMATCH"}
                    else "EXECUTOR_REJECTED"
                )
                raise ExecutorRejected(safe)
            response.raise_for_status()
            return ExecutionReceipt.model_validate_json(response.content)
        except ExecutorRejected:
            raise
        except Exception as exc:
            # Transport failure, malformed receipt and 5xx all may follow an effect.
            raise ExecutionUncertain() from exc

    def receipt(self, execution_id):
        response = self._client.get(
            f"/internal/receipts/{execution_id}", headers=self._headers
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return ExecutionReceipt.model_validate_json(response.content)

    def resource_version(self, resource_id):
        # P1 initializes the default synthetic sandbox on its first metadata
        # request. Serialize that handshake within this control process.
        with self._metadata_lock:
            response = self._client.get(
                f"/internal/resources/{quote(resource_id, safe=':')}/version",
                headers=self._headers,
            )
        response.raise_for_status()
        value = response.json()["version"]
        if type(value) is not int or value < 0:
            raise ValueError("Versión de recurso inválida")
        return value

    def close(self):
        if self._owned:
            self._client.close()
