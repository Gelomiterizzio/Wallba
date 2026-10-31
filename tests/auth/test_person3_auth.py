"""Persona 3 — real auth integration against P1's untouched application factory."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import text, update
from wallba.agent.service import seed_agents
from wallba.auth.integration import HumanAuthorizer, create_auth
from wallba.auth.models import (
    AgentCredentialRecord,
    AuthError,
    HumanRecord,
    Role,
    Scope,
)
from wallba.auth.passwords import Argon2PasswordHasher
from wallba.auth.persistence import SqliteLoginRateLimiter
from wallba.auth.routes import build_router
from wallba.auth.schema import credentials, principals
from wallba.auth.service import AuthSettings
from wallba.auth.tokens import hash_opaque_token
from wallba.foundation.app import create_app
from wallba.foundation.config import Settings
from wallba.foundation.database import (
    create_sqlite_engine,
    run_migrations,
    write_transaction,
)
from wallba.foundation.http import Integrations
from wallba.foundation.models import AgentRow

ORIGIN = "http://127.0.0.1:8080"
PASSWORD = "synthetic-person3-auth-passphrase"


class FixedClock:
    def __init__(self):
        self.instant = datetime(2026, 10, 31, 12, tzinfo=UTC)

    def now(self):
        return self.instant

    def advance(self, duration):
        self.instant += duration


@pytest.fixture
def auth_lab(tmp_path):
    data = tmp_path / "control"
    run_migrations(data / "control.sqlite")
    engine = create_sqlite_engine(data / "control.sqlite")
    with engine.connect() as connection:
        # Comprueba las tablas de P3, no la última revisión: otros dominios añaden las suyas.
        tables = set(
            connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).scalars()
        )
    assert {"principals", "sessions", "agent_credentials", "login_rate_limits"} <= tables
    seed_agents(engine)
    clock = FixedClock()
    hasher = Argon2PasswordHasher()
    service = create_auth(
        engine, AuthSettings(frozenset({ORIGIN})), clock=clock, hasher=hasher
    )
    repository = service.repository
    operator = HumanRecord(
        "demo-operator",
        "demo-operator",
        hasher.hash_password(PASSWORD),
        frozenset({Role.VIEWER, Role.OPERATOR}),
        False,
    )
    approver = HumanRecord(
        "demo-approver",
        "demo-approver",
        hasher.hash_password(PASSWORD),
        frozenset({Role.VIEWER, Role.APPROVER}),
        False,
    )
    repository.add_human(operator)
    repository.add_human(approver)
    repository.add_agent_credential(
        AgentCredentialRecord(
            hash_opaque_token("synthetic-person3-agent-secret"),
            "demo-agent",
            "demo-agent-principal",
            frozenset({Scope("file.read", "file:public-guide")}),
            None,
        )
    )
    authorizer = HumanAuthorizer(service)
    app = create_app(
        Settings(
            role="control",
            environment_id="protected-fixture",
            data_dir=data,
            executor_url="http://executor",
            executor_token="test-executor-token",
        ),
        Integrations(authorizer=authorizer, extra_routers=[build_router(service)]),
    )

    # Exercise the real integration port explicitly; no header-derived test role.
    @app.post("/api/v1/p3-test-guard")
    def guard(request: Request):
        principal = authorizer.require(request, "approver", mutation=True)
        return {"principal_id": principal.principal_id}

    @app.get("/api/v1/p3-agent-guard")
    def agent_guard(request: Request):
        principal = authorizer.require_agent_scope(
            request, "file.read", "file:public-guide"
        )
        return {"principal_id": principal.principal_id, "agent_id": principal.agent_id}

    with TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 42000)) as client:
        yield client, service, repository, authorizer, clock, engine, data
    engine.dispose()


def login(client, username="demo-operator", password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": ORIGIN},
    )


def test_login_me_logout_hashes_argon2_and_shared_slug(auth_lab):
    client, service, repository, _, _, _, _ = auth_lab
    response = login(client)
    assert response.status_code == 200
    csrf = response.json()["csrf_token"]
    token = client.cookies.get("wallba_session")
    assert token and csrf != token
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    record = repository.get_session(hash_opaque_token(token))
    assert record.csrf_hash == hash_opaque_token(csrf)
    assert token not in repr(record) and csrf not in repr(record)
    human = repository.get_human_by_username("demo-operator")
    assert human.password_hash.startswith("$argon2id$")
    assert service._hasher.verify_password(PASSWORD, human.password_hash)
    identity = client.get("/api/v1/auth/me")
    assert (
        identity.status_code == 200
        and identity.json()["principal_id"] == "demo-operator"
    )
    assert identity.json()["csrf_token"] == csrf
    assert token not in identity.text
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}
        ).status_code
        == 204
    )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_p1_agent_routes_receive_real_person3_authorizer(auth_lab):
    client, _, _, _, _, _, _ = auth_lab
    assert client.get("/api/v1/agents").status_code == 401
    login(client)
    response = client.get("/api/v1/agents")
    assert response.status_code == 200 and any(
        item["id"] == "demo-agent" for item in response.json()["items"]
    )


def test_multitab_and_stale_touch_do_not_reactivate_logout(auth_lab):
    client, _, repository, _, clock, _, _ = auth_lab
    csrf = login(client).json()["csrf_token"]
    token = client.cookies.get("wallba_session")
    stale = repository.get_session(hash_opaque_token(token))
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.get("/api/v1/auth/me"), range(6)))
    assert all(
        item.status_code == 200 and item.json()["csrf_token"] == csrf
        for item in responses
    )
    client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert repository.update_session(replace(stale, last_seen_at=clock.now())) is False
    assert repository.get_session(hash_opaque_token(token)).revoked_at is not None


@pytest.mark.parametrize(
    "origin,csrf", [(None, "valid"), ("https://evil.test", "valid"), (ORIGIN, "wrong")]
)
def test_origin_csrf_fail_closed_without_revocation(auth_lab, origin, csrf):
    client, _, _, _, _, _, _ = auth_lab
    issued = login(client).json()["csrf_token"]
    headers = {"X-CSRF-Token": issued if csrf == "valid" else csrf}
    if origin:
        headers["Origin"] = origin
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 403
    assert client.get("/api/v1/auth/me").status_code == 200


def test_human_role_and_agent_separation_on_real_guard(auth_lab):
    client, _, _, _, _, _, _ = auth_lab
    csrf = login(client).json()["csrf_token"]
    headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
    assert client.post("/api/v1/p3-test-guard", headers=headers).status_code == 403
    csrf = login(client, username="demo-approver").json()["csrf_token"]
    headers["X-CSRF-Token"] = csrf
    assert client.post("/api/v1/p3-test-guard", headers=headers).status_code == 200
    headers["Authorization"] = "Bearer synthetic-person3-agent-secret"
    assert client.post("/api/v1/p3-test-guard", headers=headers).status_code == 403


def test_agent_identity_revocation_and_scope_update(auth_lab):
    _, _, repository, _, clock, engine, _ = auth_lab
    from wallba.auth.authorization import authenticate_agent, require_scope

    principal = authenticate_agent(
        repository, "synthetic-person3-agent-secret", "test-request"
    )
    assert principal.agent_id == "demo-agent" and not hasattr(principal, "roles")
    assert not isinstance(
        require_scope(principal, "file.read", "file:public-guide", "test-request"),
        AuthError,
    )
    assert isinstance(
        require_scope(principal, "record.delete", "table:demo-records", "test-request"),
        AuthError,
    )
    with write_transaction(engine) as connection:
        connection.execute(
            update(AgentRow).where(AgentRow.id == "demo-agent").values(tools_json=[])
        )
    principal = authenticate_agent(
        repository, "synthetic-person3-agent-secret", "test-request"
    )
    assert principal.scopes == frozenset()
    with write_transaction(engine) as connection:
        connection.execute(
            update(credentials).values(revoked_at=clock.now().isoformat())
        )
    assert (
        authenticate_agent(
            repository, "synthetic-person3-agent-secret", "test-request"
        ).status_code
        == 401
    )


def test_disabled_unknown_and_bad_credentials_are_uniform(auth_lab):
    client, _, _, _, _, engine, _ = auth_lab
    responses = [login(client, username="unknown"), login(client, password="wrong")]
    with write_transaction(engine) as connection:
        connection.execute(
            update(principals)
            .where(principals.c.id == "demo-operator")
            .values(disabled=True)
        )
    responses.append(login(client))
    assert all(item.status_code == 401 for item in responses)
    assert len({item.json()["error"]["message"] for item in responses}) == 1


def test_rate_limit_survives_restart_and_atomic_reservations(auth_lab):
    _, _, _, _, clock, engine, _ = auth_lab
    limiter = SqliteLoginRateLimiter(engine, 3, 60)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(lambda _: limiter.acquire("same-peer", clock.now()), range(12))
        )
    assert sum(results) == 3
    assert not SqliteLoginRateLimiter(engine, 3, 60).acquire("same-peer", clock.now())
    clock.advance(timedelta(seconds=60))
    assert limiter.acquire("same-peer", clock.now())


def test_sessions_expire_rotate_and_survive_new_service(auth_lab):
    client, service, repository, _, clock, engine, _ = auth_lab
    csrf = login(client).json()["csrf_token"]
    token = client.cookies.get("wallba_session")
    replacement = create_auth(engine, service.settings, clock=clock)
    assert replacement.me(token, "request").csrf_token == csrf
    login(client)
    assert repository.get_session(hash_opaque_token(token)).revoked_at is not None
    clock.advance(timedelta(minutes=30))
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        '{"username":"demo-operator","password":"x","roles":["approver"]}',
        '{"username":"a","username":"b","password":"x"}',
        '{"username":null,"password":true}',
        '{"username":"a","password":"\\ud800"}',
        "[" * 1500 + "]" * 1500,
    ],
)
def test_invalid_login_payload_rejected(auth_lab, body):
    client, _, _, _, _, _, _ = auth_lab
    response = client.post(
        "/api/v1/auth/login",
        content=body,
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_cookie_ambiguity_and_media_type(auth_lab):
    client, _, _, _, _, _, _ = auth_lab
    assert (
        client.post(
            "/api/v1/auth/login", content="x", headers={"Origin": ORIGIN}
        ).status_code
        == 415
    )
    login(client)
    token = client.cookies.get("wallba_session")
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Cookie": f"wallba_session={token}; wallba_session={token}"},
        ).status_code
        == 401
    )


def test_insecure_remote_cookie_configuration_rejected():
    with pytest.raises(ValueError):
        AuthSettings(frozenset({"https://remote.test"}), cookie_secure=False)


def test_bearer_guard_rejects_ambiguous_and_unknown_headers(auth_lab):
    client, _, _, _, _, _, _ = auth_lab
    endpoint = "/api/v1/p3-agent-guard"
    bearer = "Bearer synthetic-person3-agent-secret"
    response = client.get(endpoint, headers={"Authorization": bearer})
    assert (
        response.status_code == 200
        and response.json()["principal_id"] == "demo-agent-principal"
    )
    for headers in (
        {},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer wrong"},
        [("Authorization", bearer), ("Authorization", bearer)],
    ):
        assert client.get(endpoint, headers=headers).status_code == 401


def test_absolute_expiration_cannot_be_extended_by_activity(auth_lab):
    client, _, repository, _, clock, _, _ = auth_lab
    login(client)
    key = hash_opaque_token(client.cookies.get("wallba_session"))
    original = repository.get_session(key)
    for _ in range(23):
        clock.advance(timedelta(minutes=20))
        assert client.get("/api/v1/auth/me").status_code == 200
    clock.advance(timedelta(minutes=20))
    assert clock.now() == original.expires_at
    assert client.get("/api/v1/auth/me").status_code == 401
    assert repository.get_session(key).expires_at == original.expires_at


def test_sensitive_values_are_not_logged_or_persisted_raw(auth_lab, caplog):
    client, _, repository, _, _, _, _ = auth_lab
    import logging

    caplog.set_level(logging.INFO, logger="wallba.auth")
    response = login(client)
    token = client.cookies.get("wallba_session")
    csrf = response.json()["csrf_token"]
    record = repository.get_session(hash_opaque_token(token))
    client.get("/api/v1/auth/me")
    client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    messages = "\n".join(
        item.getMessage() for item in caplog.records if item.name == "wallba.auth"
    )
    for forbidden in (PASSWORD, token, csrf, record.token_hash, record.csrf_hash):
        assert forbidden not in messages
    assert "event=login_succeeded" in messages


def test_rate_limit_http_and_socket_peer_ignore_forwarding_headers(auth_lab):
    client, _, _, _, _, _, _ = auth_lab
    for _ in range(10):
        assert login(client, password="wrong-password").status_code == 401
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "demo-operator", "password": PASSWORD},
        headers={"Origin": ORIGIN, "X-Forwarded-For": "198.51.100.1"},
    )
    assert response.status_code == 429


def test_payload_size_limit_uses_actual_bytes(auth_lab):
    client, _, _, _, _, _, _ = auth_lab
    response = client.post(
        "/api/v1/auth/login",
        content=b"x" * 65537,
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    misleading = client.post(
        "/api/v1/auth/login",
        content=b"x" * 65537,
        headers={
            "Origin": ORIGIN,
            "Content-Type": "application/json",
            "Content-Length": "1",
        },
    )
    assert misleading.status_code == 413


def test_revoked_human_session_cannot_enter_guard_or_recover_csrf(auth_lab):
    client, _, repository, _, _, _, _ = auth_lab
    response = login(client, username="demo-approver")
    raw = client.cookies.get("wallba_session")
    csrf = response.json()["csrf_token"]
    headers = {
        "Origin": ORIGIN,
        "X-CSRF-Token": csrf,
        "Cookie": f"wallba_session={raw}",
    }
    assert client.post("/api/v1/p3-test-guard", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert repository.get_session(hash_opaque_token(raw)).revoked_at is not None
    assert client.post("/api/v1/p3-test-guard", headers=headers).status_code == 401
    identity = client.get(
        "/api/v1/auth/me", headers={"Cookie": f"wallba_session={raw}"}
    )
    assert identity.status_code == 401 and "csrf_token" not in identity.text


def test_disabling_human_denies_guard_and_invalidates_session(auth_lab):
    client, _, repository, _, _, engine, _ = auth_lab
    csrf = login(client, username="demo-approver").json()["csrf_token"]
    raw = client.cookies.get("wallba_session")
    with write_transaction(engine) as connection:
        connection.execute(
            update(principals)
            .where(principals.c.id == "demo-approver")
            .values(disabled=True)
        )
    response = client.post(
        "/api/v1/p3-test-guard", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}
    )
    assert response.status_code == 401
    assert repository.get_session(hash_opaque_token(raw)).revoked_at is not None


def test_bearer_is_bound_to_exact_principal_and_revocation_is_specific(auth_lab):
    client, _, repository, _, clock, engine, _ = auth_lab
    second_secret = "synthetic-person3-scoped-reader-secret"
    repository.add_agent_credential(
        AgentCredentialRecord(
            hash_opaque_token(second_secret),
            "scoped-reader",
            "scoped-reader-principal",
            frozenset({Scope("file.read", "file:public-guide")}),
            None,
        )
    )
    endpoint = "/api/v1/p3-agent-guard"
    response = client.get(
        endpoint,
        headers={
            "Authorization": f"bEaReR {second_secret}",
            "X-Agent-ID": "demo-agent",
            "X-Principal-ID": "demo-operator",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "principal_id": "scoped-reader-principal",
        "agent_id": "scoped-reader",
    }
    with write_transaction(engine) as connection:
        connection.execute(
            update(credentials)
            .where(
                credentials.c.token_hash
                == hash_opaque_token("synthetic-person3-agent-secret")
            )
            .values(revoked_at=clock.now().isoformat())
        )
    assert (
        client.get(
            endpoint, headers={"Authorization": "Bearer synthetic-person3-agent-secret"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            endpoint, headers={"Authorization": f"Bearer {second_secret}"}
        ).status_code
        == 200
    )


def test_login_requires_origin_but_not_preexisting_csrf(auth_lab):
    client, _, _, _, _, _, _ = auth_lab
    rejected = client.post(
        "/api/v1/auth/login", json={"username": "demo-operator", "password": PASSWORD}
    )
    assert rejected.status_code == 403 and "csrf_token" not in rejected.text
    accepted = login(client)
    assert accepted.status_code == 200 and "csrf_token" in accepted.json()


def test_login_and_me_do_not_reflect_client_authority_or_context(auth_lab):
    client, _, _, _, _, _, _ = auth_lab
    marker = "attacker-supplied-context-marker"
    bad = client.post(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN},
        json={
            "username": "demo-operator",
            "password": PASSWORD,
            "principal_id": marker,
            "roles": ["approver"],
            "csrf_token": marker,
            "context": {"environment_id": marker},
        },
    )
    assert bad.status_code == 422 and marker not in bad.text
    login(client)
    response = client.get(
        "/api/v1/auth/me",
        params={"principal_id": marker, "csrf_token": marker},
        headers={"X-Principal-ID": marker, "X-Role": "approver"},
    )
    assert response.status_code == 200 and marker not in response.text
    assert response.json()["principal_id"] == "demo-operator"
    assert response.json()["roles"] == ["operator", "viewer"]
