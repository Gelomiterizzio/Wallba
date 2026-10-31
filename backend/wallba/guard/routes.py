"""Rutas del guardia. La identidad sale de la sesión, no del cuerpo."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from wallba.foundation.http import ApiError
from wallba.guard.errors import GuardError
from wallba.guard.hook import snippet
from wallba.guard.runtime import GuardRuntime

WRITERS = frozenset({"operator", "policy_admin"})
READERS = WRITERS | frozenset({"viewer", "approver"})


class OpenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_path: str = Field(min_length=1, max_length=1024)


class RuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relative_path: str = Field(min_length=1, max_length=512)
    kind: str
    posture: str


class ProbeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relative_path: str = Field(min_length=1, max_length=512)
    operation: str
    apply: bool = False
    content: str | None = Field(default=None, max_length=200)


class RemoveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str


def create_guard_router(runtime: GuardRuntime, authorizer) -> APIRouter:
    router = APIRouter(prefix="/guard", tags=["guard"])

    def reader(request: Request):
        if authorizer is None:
            raise ApiError(503, "AUTHORIZATION_UNAVAILABLE", "Autorización no disponible")
        principal = authorizer.authenticate(request)
        if not any(role in principal.roles for role in READERS):
            raise ApiError(403, "ROLE_DENIED", "Permiso insuficiente para esta operación.")
        return principal

    def writer(request: Request):
        principal = reader(request)
        authorizer.require_csrf(request)
        if not any(role in principal.roles for role in WRITERS):
            raise ApiError(403, "ROLE_DENIED", "Permiso insuficiente para esta operación.")
        return principal

    def run(action):
        try:
            return action()
        except GuardError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from exc

    @router.get("/overview")
    def overview(request: Request) -> dict:
        reader(request)
        projects = runtime.store.projects()
        if not projects:
            return {"project": None, "summary": None}
        return {"project": projects[0]["id"], "summary": runtime.summary(projects[0]["id"])}

    @router.get("/hook-snippet")
    def hook_snippet(request: Request) -> dict:
        reader(request)
        return {
            "snippet": snippet(),
            "installed": False,
            "note": "WALLBA no modifica la configuración de Claude Code ni de otras herramientas.",
        }

    @router.post("/projects")
    def open_project(body: OpenBody, request: Request) -> dict:
        writer(request)
        return run(lambda: runtime.open_project(body.root_path))

    @router.post("/samples")
    def sample(request: Request) -> dict:
        writer(request)
        return run(runtime.create_sample)

    @router.get("/projects/{project_id}/children")
    def children(project_id: str, request: Request, path: str = "") -> dict:
        reader(request)
        return {"entries": run(lambda: runtime.children(project_id, path))}

    @router.post("/projects/{project_id}/rules")
    def add_rule(project_id: str, body: RuleBody, request: Request) -> dict:
        writer(request)
        run(lambda: runtime.protect(project_id, body.relative_path, body.kind, body.posture))
        return runtime.summary(project_id)

    @router.post("/projects/{project_id}/rules/remove")
    def remove_rule(project_id: str, body: RemoveBody, request: Request) -> dict:
        writer(request)
        run(lambda: runtime.remove_rule(project_id, body.rule_id))
        return {"removed": body.rule_id}

    @router.post("/projects/{project_id}/probe")
    def probe(project_id: str, body: ProbeBody, request: Request) -> dict:
        writer(request)
        if body.operation not in {"read", "write", "delete"}:
            raise ApiError(422, "VALIDATION_ERROR", "La operación no es válida.")
        return run(
            lambda: runtime.probe(
                project_id,
                body.relative_path,
                body.operation,
                apply=body.apply,
                content=body.content,
            )
        )

    @router.post("/projects/{project_id}/watch")
    def watch(project_id: str, request: Request) -> dict:
        writer(request)
        found = run(lambda: runtime.watch_once(project_id))
        return {"detected": len(found), "events": runtime.events(project_id)}

    @router.get("/projects/{project_id}/events")
    def events(project_id: str, request: Request) -> dict:
        reader(request)
        return {"events": run(lambda: runtime.events(project_id))}

    @router.get("/projects/{project_id}/summary")
    def summary(project_id: str, request: Request) -> dict:
        reader(request)
        return run(lambda: runtime.summary(project_id))

    return router
