import { useEffect, useId, useState } from "react"
import {
  activationAccepted,
  activationConflict,
  applyRemoteFailure,
  canActivate,
  createDraft,
  editDraft,
  markBusy,
  readRules,
  rememberActive,
  semanticDiff,
  setFormat,
  validationAccepted,
  versionConfirmed,
  versionSaved,
  type PolicyDraft,
} from "./draftState"
import { PolicyRequestError, type PolicyApi } from "./policyApi"
import "./policies.css"

type PolicyEditorPageProps = {
  client: PolicyApi
  policyId: string
  canAdmin: boolean
  initialDraft?: string
  initialFormat?: "yaml" | "json"
  activeDocument?: unknown
  activeVersion?: number | null
  activeChecksum?: string | null
  exampleData?: boolean
  autoload?: boolean
}

export function PolicyEditorPage({
  client,
  policyId,
  canAdmin,
  initialDraft = "",
  initialFormat = "yaml",
  activeDocument = null,
  activeVersion = null,
  activeChecksum = null,
  exampleData = false,
  autoload = true,
}: PolicyEditorPageProps) {
  const [draft, setDraft] = useState<PolicyDraft>(() =>
    rememberActive(createDraft(policyId, initialDraft, initialFormat), activeVersion, activeChecksum),
  )
  const [activePointer, setActivePointer] = useState<{ policyId: string; version: number } | null>(
    activeVersion == null ? null : { policyId, version: activeVersion },
  )
  const [activeRules, setActiveRules] = useState<unknown>(activeDocument)
  const [confirming, setConfirming] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const formatId = useId()
  const draftId = useId()
  const errorId = useId()
  const candidate = readStoredRules(draft.normalizedText)
  const difference = semanticDiff(readRules(activeRules), candidate)
  const activateEnabled = canActivate(draft, canAdmin)

  useEffect(() => {
    if (!autoload || activeDocument != null || activeVersion != null || initialDraft.length > 0) {
      return
    }
    let cancelled = false
    client
      .list()
      .then(async (page) => {
        const globalActive = page.items.find((item) => item.active)
        if (!cancelled) {
          setActivePointer(
            globalActive ? { policyId: globalActive.policy_id, version: globalActive.version } : null,
          )
        }
        const active = globalActive?.policy_id === policyId ? globalActive : undefined
        if (!active || cancelled) {
          return
        }
        const detail = await client.getVersion(policyId, active.version)
        if (cancelled) {
          return
        }
        setActiveRules(detail.document)
        setDraft((current) => {
          const located = rememberActive(current, active.version, active.checksum)
          if (current.draftSource.length > 0) {
            return located
          }
          return editDraft({ ...located, format: "json" }, JSON.stringify(detail.document, null, 2))
        })
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setNotice(failureMessage(reason))
        }
      })
    return () => {
      cancelled = true
    }
  }, [autoload, activeDocument, activeVersion, client, initialDraft.length, policyId])

  async function validate() {
    const source = draft.draftSource
    const format = draft.format
    setDraft((current) => markBusy(current))
    setNotice(null)
    try {
      const result = await client.validate(format, source)
      setDraft((current) => validationAccepted(current, source, result.normalized))
    } catch (reason) {
      reportFailure(reason)
    }
  }

  async function save() {
    const source = draft.draftSource
    const normalized = draft.normalizedText
    if (normalized == null || draft.validatedSource !== source) {
      return
    }
    setDraft((current) => markBusy(current))
    try {
      const created = await client.createVersion(policyId, JSON.parse(normalized) as unknown)
      const confirmed = await client.getVersion(policyId, created.version)
      setDraft((current) => {
        if (current.draftSource !== source || current.normalizedText !== normalized) {
          return { ...current, busy: false }
        }
        return versionConfirmed(versionSaved(current, created.version), confirmed.version)
      })
      setNotice(`Versión ${confirmed.version} guardada. La activa no cambió.`)
    } catch (reason) {
      reportFailure(reason)
    }
  }

  async function activate() {
    const savedVersion = draft.savedVersion
    const expected = draft.activeVersion
    if (!canActivate(draft, canAdmin) || savedVersion == null) {
      return
    }
    setDraft((current) => markBusy(current))
    setConfirming(false)
    try {
      const expectedVersion = activePointer ? activePointer.version : expected
      const result = await client.activate(policyId, savedVersion, expectedVersion, activePointer?.policyId ?? null)
      setActivePointer({ policyId, version: result.version })
      setDraft((current) => activationAccepted(current, result.version, result.checksum))
      setNotice(`Versión ${result.version} activada.`)
    } catch (reason) {
      if (reason instanceof PolicyRequestError && reason.status === 409) {
        await refreshActive()
        return
      }
      reportFailure(reason)
    }
  }

  function reportFailure(reason: unknown) {
    if (!(reason instanceof PolicyRequestError)) {
      setDraft((current) => ({ ...current, busy: false }))
      setNotice("No se pudo completar la operación.")
      return
    }
    const outcome = applyRemoteFailure(createDraft(policyId), reason.status, reason.details)
    setNotice(outcome.message)
    setDraft((current) => applyRemoteFailure(current, reason.status, reason.details).state)
  }

  async function refreshActive() {
    try {
      const page = await client.list()
      const globalActive = page.items.find((item) => item.active)
      setActivePointer(globalActive ? { policyId: globalActive.policy_id, version: globalActive.version } : null)
      const active = globalActive?.policy_id === policyId ? globalActive : undefined
      if (!active) {
        setActiveRules(null)
        setDraft((current) => activationConflict(current, null, null))
        setNotice("No hay una versión activa de esta política. No se reintentó la activación.")
        return
      }
      const detail = await client.getVersion(policyId, active.version)
      setActiveRules(detail.document)
      setDraft((current) => activationConflict(current, active.version, active.checksum))
      setNotice("La versión activa cambió. Revisa la comparación antes de volver a intentar.")
    } catch {
      setDraft((current) => applyRemoteFailure(current, 503).state)
      setNotice("No se pudo releer la versión activa. No se reintentó la activación.")
    }
  }

  return (
    <section className="policy-feature" aria-busy={draft.busy}>
      <h1>Editor de {policyId}</h1>
      {exampleData ? <p className="policy-example">DATOS DE EJEMPLO</p> : null}
      <p>
        Versión activa: {draft.activeVersion == null ? "ninguna" : draft.activeVersion}
        {draft.activeChecksum ? <code> {draft.activeChecksum.slice(0, 12)}</code> : null}
      </p>
      <label htmlFor={formatId}>Formato</label>
      <select
        id={formatId}
        value={draft.format}
        onChange={(event) => setDraft((current) => setFormat(current, event.target.value === "json" ? "json" : "yaml"))}
      >
        <option value="yaml">YAML</option>
        <option value="json">JSON</option>
      </select>
      <label htmlFor={draftId}>Borrador</label>
      <textarea
        id={draftId}
        value={draft.draftSource}
        spellCheck={false}
        aria-invalid={draft.errors.length > 0}
        aria-describedby={draft.errors.length > 0 ? errorId : undefined}
        onChange={(event) => {
          setConfirming(false)
          setDraft((current) => editDraft(current, event.target.value))
        }}
      />
      <button type="button" onClick={() => void validate()} disabled={draft.busy || draft.draftSource.length === 0}>
        Validar
      </button>
      <button type="button" onClick={() => void save()} disabled={draft.busy || draft.validatedSource !== draft.draftSource}>
        Guardar versión
      </button>
      <button type="button" onClick={() => setConfirming(true)} disabled={!activateEnabled}>
        Activar
      </button>
      {draft.errors.length > 0 ? (
        <div className="policy-panel" id={errorId} role="alert" aria-live="polite" tabIndex={-1}>
          <h2>Errores</h2>
          <ul>
            {draft.errors.map((error) => (
              <li key={`${error.field}-${error.code}`} className="policy-error">
                {error.field}: {error.code}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="policy-panel">
        <h2>Comparación</h2>
        <ul>
          <li>Reglas nuevas: {difference.added.join(", ") || "ninguna"}</li>
          <li>Reglas retiradas: {difference.removed.join(", ") || "ninguna"}</li>
          <li>Reglas modificadas: {difference.changed.join(", ") || "ninguna"}</li>
        </ul>
      </div>
      {draft.conflictMessage ? (
        <p className="policy-error" role="alert">
          {draft.conflictMessage}
        </p>
      ) : null}
      {notice ? <p aria-live="polite">{notice}</p> : null}
      {confirming ? (
        <div
          className="policy-panel"
          role="dialog"
          aria-labelledby={`${draftId}-confirm`}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setConfirming(false)
            }
          }}
        >
          <h2 id={`${draftId}-confirm`}>Confirmar activación</h2>
          <p>
            Vas a activar {policyId}, versión {draft.savedVersion}, en lugar de la versión{" "}
            {draft.activeVersion == null ? "ninguna" : draft.activeVersion}.
          </p>
          <button type="button" onClick={() => void activate()}>
            Confirmar activación
          </button>
          <button type="button" onClick={() => setConfirming(false)}>
            Cancelar
          </button>
        </div>
      ) : null}
    </section>
  )
}

function readStoredRules(text: string | null) {
  if (text == null) {
    return []
  }
  try {
    return readRules(JSON.parse(text) as unknown)
  } catch {
    return []
  }
}

function failureMessage(reason: unknown): string {
  if (reason instanceof PolicyRequestError) {
    return applyRemoteFailure(createDraft("demo-policy"), reason.status, reason.details).message
  }
  return "No se pudo cargar la política activa."
}
