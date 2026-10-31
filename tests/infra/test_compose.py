"""Aislamiento declarado en Compose e imágenes (WAL-P1-009).

Estas pruebas leen la configuración; test_live_isolation.py comprueba la red real.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
COMPOSE = yaml.safe_load((INFRA / "compose.yaml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]


def _networks(service: str) -> set[str]:
    return set(SERVICES[service]["networks"])


def test_agent_shares_no_network_with_executors() -> None:
    assert not _networks("agent") & _networks("executor")
    assert not _networks("agent") & _networks("baseline")


def test_agent_only_reaches_the_api() -> None:
    assert _networks("agent") <= _networks("api")


def test_agent_has_no_volumes_and_only_its_bearer() -> None:
    assert "volumes" not in SERVICES["agent"]
    assert SERVICES["agent"]["secrets"] == ["agent_bearer"]


def test_agent_environment_has_no_executor_details() -> None:
    environment = SERVICES["agent"]["environment"]
    assert not {key for key in environment if "EXECUTOR" in key or "CAPABILITY" in key or "DATA_DIR" in key}


def test_baseline_has_no_capability_secret_and_no_route_to_protected() -> None:
    assert "capability_secret" not in SERVICES["baseline"]["secrets"]
    assert "executor_token" not in SERVICES["baseline"]["secrets"]
    assert not _networks("baseline") & _networks("executor")


def test_executor_and_baseline_do_not_share_volumes_or_credentials() -> None:
    assert not set(SERVICES["executor"]["volumes"]) & set(SERVICES["baseline"]["volumes"])
    assert not set(SERVICES["executor"]["secrets"]) & set(SERVICES["baseline"]["secrets"])


def test_capability_secret_is_limited_to_api_and_executor() -> None:
    holders = {name for name, service in SERVICES.items() if "capability_secret" in service.get("secrets", [])}
    assert holders == {"api", "executor"}


def test_only_web_publishes_a_port_and_only_on_loopback() -> None:
    published = {name: service["ports"] for name, service in SERVICES.items() if "ports" in service}
    assert set(published) == {"web"}
    assert published["web"] == ["127.0.0.1:8080:8080"]


def test_internal_networks_have_no_egress() -> None:
    for name, network in COMPOSE["networks"].items():
        if name != "edge":
            assert network.get("internal") is True, name
    assert "edge" not in _networks("api") | _networks("agent") | _networks("executor")


def test_baseline_and_agent_only_exist_in_demo_profile() -> None:
    assert SERVICES["baseline"]["profiles"] == ["demo"]
    assert SERVICES["agent"]["profiles"] == ["demo"]


@pytest.mark.parametrize("service", ["api", "executor", "baseline", "agent", "web"])
def test_services_are_hardened(service: str) -> None:
    config = SERVICES[service]
    assert config["read_only"] is True
    assert config["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in config["security_opt"]


def test_no_docker_socket_or_host_mounts() -> None:
    for name, service in SERVICES.items():
        for volume in service.get("volumes", []):
            source = volume.split(":")[0]
            assert source in COMPOSE["volumes"], f"{name} monta {source} del host"


def test_data_volumes_carry_project_label() -> None:
    for volume in COMPOSE["volumes"].values():
        assert volume["labels"]["com.wallba.project"] == "true"


def test_build_context_is_an_allowlist_without_secrets() -> None:
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert lines[lines.index("*")] == "*"
    assert not [line for line in lines if line.startswith("!") and ("secrets" in line or ".git" in line)]


def test_secrets_are_outside_git() -> None:
    assert re.search(r"^secrets/$", (ROOT / ".gitignore").read_text(encoding="utf-8"), re.M)
    tracked = subprocess.run(["git", "ls-files", "secrets"], cwd=ROOT, capture_output=True, text=True, check=False)
    assert tracked.stdout.strip() == ""


@pytest.mark.parametrize("name", ["Dockerfile.api", "Dockerfile.executor", "Dockerfile.agent"])
def test_images_run_as_non_root_and_install_from_lock(name: str) -> None:
    text = (INFRA / name).read_text(encoding="utf-8")
    assert re.search(r"^USER wallba$", text, re.M)
    assert "uv sync --frozen" in text
    assert ":latest" not in text


def _copied_paths(dockerfile: str) -> list[str]:
    text = (INFRA / dockerfile).read_text(encoding="utf-8")
    return re.findall(r"^COPY (backend/wallba\S*) ", text, re.M)


def _materialize(tmp_path: Path, dockerfile: str) -> Path:
    """Reproduce el contenido Python de la imagen a partir de sus COPY."""
    target = tmp_path / "image"
    for source in _copied_paths(dockerfile):
        origin = ROOT / source
        destination = target / Path(source).relative_to("backend")
        if origin.is_dir():
            shutil.copytree(origin, destination, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(origin, destination)
    return target


def _import_in_image(root: Path, statement: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", statement],
        cwd=root,
        env={"PYTHONPATH": str(root), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        capture_output=True,
        text=True,
        check=False,
    )


def test_agent_image_runs_and_has_no_executor_code(tmp_path: Path) -> None:
    root = _materialize(tmp_path, "Dockerfile.agent")
    assert _import_in_image(root, "import wallba.agent.worker").returncode == 0
    assert not (root / "wallba" / "executor").exists()
    assert not (root / "wallba" / "demo").exists()
    failed = _import_in_image(root, "import wallba.executor.service")
    assert failed.returncode != 0


def test_executor_image_runs_and_has_no_agent_or_runner(tmp_path: Path) -> None:
    root = _materialize(tmp_path, "Dockerfile.executor")
    result = _import_in_image(root, "import wallba.executor.app")
    assert result.returncode == 0, result.stderr
    assert not (root / "wallba" / "agent").exists()
    assert not (root / "wallba" / "demo" / "runner.py").exists()


def test_dev_secret_generator_never_overwrites(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate_dev_secrets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    created = module.generate(tmp_path)
    assert len(created) == 4
    first = (tmp_path / "executor_token").read_text(encoding="ascii")
    assert len(first) >= 32
    assert module.generate(tmp_path) == []
    assert (tmp_path / "executor_token").read_text(encoding="ascii") == first
    if os.name == "posix":
        # Los contenedores corren con uid 10001: un archivo 0600 del host no sería legible.
        assert stat.S_IMODE((tmp_path / "executor_token").stat().st_mode) == 0o644
        assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700


def test_ci_uses_pinned_actions_and_minimal_permissions() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    assert workflow["permissions"] == {"contents": "read"}
    for action in re.findall(r"uses: (\S+)", text):
        assert re.search(r"@[0-9a-f]{40}$", action), action


def test_ci_does_not_use_hash_files_at_job_level() -> None:
    # GitHub rechaza todo el workflow si hashFiles aparece en el `if` de un job.
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    for name, job in workflow["jobs"].items():
        assert "hashFiles" not in str(job.get("if", "")), name
