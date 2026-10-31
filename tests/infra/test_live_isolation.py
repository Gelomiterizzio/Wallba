"""Aislamiento sobre la red real de Compose. Requiere Docker (WAL-P1-009).

Levanta un proyecto propio y desechable (`wallba-isolation-test`), sin tocar volúmenes
de una demo. Sin Docker o sin secretos, las pruebas quedan SKIPPED: no cuentan como superadas.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = [
    "docker", "compose",
    "-p", "wallba-isolation-test",
    "-f", str(ROOT / "infra" / "compose.yaml"),
    "--profile", "demo",
]
SECRETS = ("capability_secret", "executor_token", "baseline_token", "agent_bearer")
STARTUP_TIMEOUT_SECONDS = 120
CONNECT = (
    "import socket,sys\n"
    "s=socket.socket();s.settimeout(3)\n"
    "try:\n"
    "    s.connect((sys.argv[1],int(sys.argv[2])))\n"
    "except OSError:\n"
    "    sys.exit(7)\n"
    "sys.exit(0)\n"
)
HTTP_STATUS = (
    "import sys,urllib.request,urllib.error\n"
    "req=urllib.request.Request(sys.argv[1],method=sys.argv[2],data=b'{}',"
    "headers={'Content-Type':'application/json'})\n"
    "try:\n"
    "    print(urllib.request.urlopen(req,timeout=5).status)\n"
    "except urllib.error.HTTPError as e:\n"
    "    print(e.code)\n"
)


def _docker_ready() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0
    except OSError:
        return False


def _secrets_ready() -> bool:
    return all((ROOT / "secrets" / name).is_file() for name in SECRETS)


pytestmark = [
    pytest.mark.skipif(not _docker_ready(), reason="demonio Docker no disponible"),
    pytest.mark.skipif(not _secrets_ready(), reason="ejecutar scripts/generate_dev_secrets.py"),
]


def _compose(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*COMPOSE, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env={**os.environ, "WALLBA_DEMO_ENABLED": "true"},
    )


def _in_service(service: str, *command: str) -> subprocess.CompletedProcess[str]:
    return _compose("exec", "-T", service, *command)


def _service_logs() -> str:
    return _compose("logs", "--no-color", "--tail", "30", "api", "executor", "baseline").stdout


@pytest.fixture(scope="module")
def stack() -> Iterator[None]:
    up = _compose("up", "-d", "--build", "--wait", "--wait-timeout", "90", "api", "executor", "baseline", timeout=600)
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    try:
        assert up.returncode == 0, f"{up.stderr}\n{_service_logs()}"
        while time.monotonic() < deadline:
            if _in_service("api", "python", "-c", CONNECT, "127.0.0.1", "8000").returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail(f"la API no arrancó a tiempo\n{_service_logs()}")
        yield
    finally:
        _compose("down", "-v", "--remove-orphans")


def _from_agent(*command: str) -> subprocess.CompletedProcess[str]:
    return _compose("run", "--rm", "--no-deps", "-T", "agent", *command)


@pytest.mark.parametrize(("host", "port"), [("executor", "8001"), ("baseline", "8002")])
def test_positive_control_api_reaches_executors(stack: None, host: str, port: str) -> None:
    # Sin este control, un ejecutor caído haría pasar la prueba negativa.
    assert _in_service("api", "python", "-c", CONNECT, host, port).returncode == 0


@pytest.mark.parametrize(("host", "port"), [("executor", "8001"), ("baseline", "8002")])
def test_agent_cannot_reach_executors(stack: None, host: str, port: str) -> None:
    assert _from_agent("python", "-c", CONNECT, host, port).returncode == 7


def test_agent_can_reach_the_api(stack: None) -> None:
    assert _from_agent("python", "-c", CONNECT, "api", "8000").returncode == 0


def test_agent_has_no_internet_egress(stack: None) -> None:
    assert _from_agent("python", "-c", CONNECT, "1.1.1.1", "443").returncode == 7


def test_agent_only_has_its_bearer_and_no_data_volume(stack: None) -> None:
    listing = _from_agent("python", "-c", "import os;print(os.listdir('/run/secrets'));print(os.path.exists('/data'))")
    assert listing.returncode == 0, listing.stderr
    assert "agent_bearer" in listing.stdout
    assert "capability_secret" not in listing.stdout
    assert "executor_token" not in listing.stdout
    assert "False" in listing.stdout


def test_baseline_cannot_reach_protected_executor(stack: None) -> None:
    assert _in_service("baseline", "python", "-c", CONNECT, "executor", "8001").returncode == 7


def test_direct_executor_call_without_token_is_rejected(stack: None) -> None:
    result = _in_service("api", "python", "-c", HTTP_STATUS, "http://executor:8001/internal/execute", "POST")
    assert result.stdout.strip() == "401"


def test_protected_executor_has_no_unsafe_route(stack: None) -> None:
    result = _in_service("api", "python", "-c", HTTP_STATUS, "http://executor:8001/internal/baseline/execute", "POST")
    assert result.stdout.strip() == "404"


def test_only_web_publishes_ports(stack: None) -> None:
    published = _compose("ps", "--format", "{{.Name}} {{.Publishers}}")
    assert "0.0.0.0" not in published.stdout
    assert "127.0.0.1:8080" not in published.stdout


def test_api_runs_without_ports_of_others_failing_closed(stack: None) -> None:
    result = _in_service(
        "api", "python", "-c", HTTP_STATUS.replace("data=b'{}',", "data=None,"),
        "http://127.0.0.1:8000/api/v1/agents", "GET",
    )
    assert result.stdout.strip() == "503"


REAL_EXECUTION_SCRIPT = """
import json, secrets, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from wallba.contracts.canonical import CanonicalRequest
from wallba.contracts.capability import Capability, capability_signing_bytes, compute_signature
from wallba.contracts.fixture_ids import target_record_id
from wallba.contracts.tool_call import TOOL_CALL_ADAPTER

key = Path("/run/secrets/capability_secret").read_bytes().strip()
protected = httpx.Client(base_url="http://executor:8001", headers={
    "Authorization": "Bearer " + Path("/run/secrets/executor_token").read_text().strip()})
baseline = httpx.Client(base_url="http://baseline:8002", headers={
    "Authorization": "Bearer " + Path("/run/secrets/baseline_token").read_text().strip()})

run_id, seed = str(uuid.uuid4()), 7
left = baseline.post("/internal/environments", json={"run_id": run_id, "seed": seed}).json()
right = protected.post("/internal/environments", json={"run_id": run_id, "seed": seed}).json()
call = TOOL_CALL_ADAPTER.validate_python({
    "request_id": str(uuid.uuid4()), "agent_id": "demo-agent", "tool": "record.delete",
    "operation": "delete", "resource_id": "table:demo-records",
    "parameters": {"record_id": target_record_id(seed)}})
request = CanonicalRequest(
    call=call, principal_id="demo-operator", environment_id="protected-fixture", resource_version=1)
expires = (datetime.now(timezone.utc) + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
unsigned = Capability(
    execution_id=str(uuid.uuid4()), request_digest=request.digest(), principal_id=request.principal_id,
    environment_id=request.environment_id, resource_version=1, policy_id="demo-policy", policy_version=1,
    expires_at=expires, nonce=secrets.token_hex(16), key_id="dev-key-1", signature="0" * 64)
capability = unsigned.model_copy(update={
    "signature": compute_signature(capability_signing_bytes(unsigned), key)})
body = {"request": request.model_dump(mode="json"), "capability": capability.model_dump(mode="json")}
forged = {**body, "capability": {**body["capability"], "signature": "f" * 64}}

out = {
    "same_initial_digest": left["snapshot"]["state_digest"] == right["snapshot"]["state_digest"],
    "forged_status": protected.post("/internal/execute", json=forged).status_code,
    "after_forged": protected.get(f"/internal/environments/{run_id}").json()["snapshot"]["record_count"],
}
first = protected.post("/internal/execute", json=body)
second = protected.post("/internal/execute", json=body)
out.update({
    "first_status": first.status_code,
    "effect_count": first.json()["effect_count"],
    "replay_same_receipt": first.json() == second.json(),
    "after_execute": protected.get(f"/internal/environments/{run_id}").json()["snapshot"],
    "receipt_recovered": protected.get("/internal/receipts/" + capability.execution_id).status_code,
    "baseline_untouched": baseline.get(f"/internal/environments/{run_id}").json()["snapshot"]["record_count"],
    "baseline_token_on_protected": httpx.post(
        "http://executor:8001/internal/execute", json=body,
        headers={"Authorization": baseline.headers["Authorization"]}).status_code,
})
print(json.dumps(out))
"""


def test_real_processes_apply_capability_with_single_effect(stack: None) -> None:
    result = _in_service("api", "python", "-c", REAL_EXECUTION_SCRIPT)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["same_initial_digest"] is True
    assert observed["forged_status"] == 403
    assert observed["after_forged"] == 8
    assert observed["first_status"] == 200
    assert observed["effect_count"] == 1
    assert observed["replay_same_receipt"] is True
    assert observed["after_execute"]["record_count"] == 7
    assert observed["after_execute"]["journal_count"] == 1
    assert observed["receipt_recovered"] == 200
    assert observed["baseline_untouched"] == 8
    assert observed["baseline_token_on_protected"] == 401


def test_containers_run_as_non_root(stack: None) -> None:
    for service in ("api", "executor", "baseline"):
        result = _in_service(service, "python", "-c", "import os;print(os.getuid())")
        assert result.stdout.strip() == "10001", service
