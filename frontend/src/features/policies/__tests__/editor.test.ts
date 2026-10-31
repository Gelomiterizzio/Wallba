import assert from "node:assert/strict"
import { test } from "node:test"
import {
  applyRemoteFailure,
  canActivate,
  createDraft,
  editDraft,
  rememberActive,
  validationAccepted,
  validationRejected,
  versionConfirmed,
  versionSaved,
} from "../draftState.ts"

test("un borrador inválido conserva el texto y no habilita la activación", () => {
  const source = "schema_version: '1'\npriority: 1\n"
  const draft = editDraft(createDraft("demo-policy", source, "yaml"), source)
  const activeVersion = draft.activeVersion
  const rejected = validationRejected(draft, [{ field: "priority", code: "unknown_field" }])
  assert.equal(rejected.draftSource, source)
  assert.equal(rejected.activeVersion, activeVersion)
  assert.equal(canActivate(rejected, true), false)
})

test("editar después de validar invalida el resultado anterior", () => {
  const validated = validationAccepted(createDraft("demo-policy", "uno", "yaml"), "uno", { schema_version: "1" })
  const edited = editDraft(validated, "dos")
  assert.equal(edited.validatedSource, null)
  assert.equal(canActivate(versionConfirmed(versionSaved(edited, 1), 1), true), false)
})

test("422, 403 y 503 conservan el borrador y no tocan la versión activa", () => {
  const source = "schema_version: '1'\n"
  const ready = rememberActive(
    versionConfirmed(versionSaved(validationAccepted(createDraft("demo-policy", source, "yaml"), source, { rules: [] }), 2), 2),
    1,
    "a".repeat(64),
  )
  const invalid = applyRemoteFailure(ready, 422, [{ field: "priority", code: "unknown_field" }])
  assert.equal(invalid.state.draftSource, source)
  assert.equal(invalid.state.activeVersion, 1)
  assert.equal(invalid.refreshActive, false)
  assert.equal(canActivate(invalid.state, true), false)

  const forbidden = applyRemoteFailure(ready, 403)
  assert.equal(forbidden.state.draftSource, source)
  assert.equal(forbidden.state.accessDenied, true)
  assert.equal(canActivate(forbidden.state, true), false)

  const unavailable = applyRemoteFailure(ready, 503)
  assert.equal(unavailable.state.validatedSource, source)
  assert.equal(unavailable.state.activeVersion, 1)
  assert.equal(canActivate(unavailable.state, true), true)
})

test("activar exige validación del texto actual y versión confirmada", () => {
  let draft = validationAccepted(createDraft("demo-policy", "regla", "json"), "regla", {
    rules: [{ id: "deny-delete", effect: "DENY", tools: ["record.delete"], resources: ["table:demo-records"] }],
  })
  draft = versionSaved(draft, 3)
  assert.equal(canActivate(draft, true), false)
  draft = versionConfirmed(draft, 3)
  assert.equal(canActivate(draft, true), true)
  assert.equal(canActivate(draft, false), false)
})
