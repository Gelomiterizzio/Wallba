import assert from "node:assert/strict"
import { test } from "node:test"
import { readPolicyError } from "../policyApi.ts"
import {
  activationConflict,
  applyRemoteFailure,
  canActivate,
  createDraft,
  rememberActive,
  semanticDiff,
  validationAccepted,
  versionConfirmed,
  versionSaved,
} from "../draftState.ts"

test("un 409 pide releer la activa y conserva el borrador", () => {
  const draft = versionConfirmed(versionSaved(validationAccepted(createDraft("demo-policy", "regla", "json"), "regla", { rules: [] }), 2), 2)
  const outcome = applyRemoteFailure(draft, 409)
  assert.equal(outcome.refreshActive, true)
  assert.equal(outcome.state.draftSource, "regla")
  assert.equal(canActivate(outcome.state, true), false)
})

test("un 409 refresca la versión activa y no deja la activación habilitada", () => {
  let draft = rememberActive(createDraft("demo-policy", "regla", "json"), 1, "a".repeat(64))
  draft = validationAccepted(draft, "regla", { rules: [] })
  draft = versionConfirmed(versionSaved(draft, 2), 2)
  assert.equal(canActivate(draft, true), true)
  const conflict = activationConflict(draft, 4, "b".repeat(64))
  assert.equal(conflict.draftSource, "regla")
  assert.equal(conflict.activeVersion, 4)
  assert.equal(conflict.activeChecksum, "b".repeat(64))
  assert.equal(canActivate(conflict, true), false)
  assert.match(conflict.conflictMessage ?? "", /versión activa cambió/)
})

test("la comparación semántica distingue reglas nuevas y modificadas", () => {
  const diff = semanticDiff(
    [{ id: "allow-public-read", effect: "ALLOW", tools: ["file.read"], resources: ["file:public-guide"] }],
    [
      { id: "allow-public-read", effect: "DENY", tools: ["file.read"], resources: ["file:public-guide"] },
      { id: "allow-demo-query", effect: "ALLOW", tools: ["db.query"], resources: ["query:demo-records"] },
    ],
  )
  assert.deepEqual(diff.added, ["allow-demo-query"])
  assert.deepEqual(diff.removed, [])
  assert.deepEqual(diff.changed, ["allow-public-read"])
})

test("un error HTTP de validación no incluye el cuerpo como mensaje de éxito", () => {
  const error = readPolicyError(422, {
    error: {
      code: "POLICY_INVALID",
      message: "La política no supera la validación.",
      request_id: "11111111-1111-4111-8111-111111111111",
      details: [{ field: "priority", code: "unknown_field" }],
    },
  })
  assert.equal(error.status, 422)
  assert.equal(error.code, "POLICY_INVALID")
  assert.deepEqual(error.details, [{ field: "priority", code: "unknown_field" }])
})
