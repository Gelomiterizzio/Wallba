/** Estado del editor. Validar o fallar no cambia la versión activa. */

export type FieldError = {
  field: string
  code: string
}

export type RuleView = {
  id: string
  effect: string
  tools: string[]
  resources: string[]
}

export type PolicyDraft = {
  policyId: string
  draftSource: string
  format: "yaml" | "json"
  validatedSource: string | null
  normalizedText: string | null
  savedVersion: number | null
  confirmedVersion: number | null
  activeVersion: number | null
  activeChecksum: string | null
  errors: FieldError[]
  busy: boolean
  conflictMessage: string | null
  accessDenied: boolean
}

export type RemoteOutcome = {
  state: PolicyDraft
  message: string
  refreshActive: boolean
}

export type SemanticDiff = {
  added: string[]
  removed: string[]
  changed: string[]
}

export function createDraft(policyId: string, source = "", format: "yaml" | "json" = "yaml"): PolicyDraft {
  return {
    policyId,
    draftSource: source,
    format,
    validatedSource: null,
    normalizedText: null,
    savedVersion: null,
    confirmedVersion: null,
    activeVersion: null,
    activeChecksum: null,
    errors: [],
    busy: false,
    conflictMessage: null,
    accessDenied: false,
  }
}

export function editDraft(state: PolicyDraft, source: string): PolicyDraft {
  return {
    ...state,
    draftSource: source,
    validatedSource: null,
    normalizedText: null,
    confirmedVersion: null,
    errors: [],
    conflictMessage: null,
  }
}

export function setFormat(state: PolicyDraft, format: "yaml" | "json"): PolicyDraft {
  if (state.format === format) {
    return state
  }
  return editDraft({ ...state, format }, state.draftSource)
}

export function markBusy(state: PolicyDraft): PolicyDraft {
  return { ...state, busy: true }
}

export function validationRejected(state: PolicyDraft, errors: FieldError[]): PolicyDraft {
  return {
    ...state,
    errors,
    validatedSource: null,
    normalizedText: null,
    confirmedVersion: null,
    busy: false,
  }
}

export function validationAccepted(state: PolicyDraft, source: string, normalized: unknown): PolicyDraft {
  if (source !== state.draftSource) {
    return { ...state, busy: false }
  }
  return {
    ...state,
    validatedSource: source,
    normalizedText: JSON.stringify(normalized),
    errors: [],
    busy: false,
  }
}

export function versionSaved(state: PolicyDraft, version: number): PolicyDraft {
  return {
    ...state,
    savedVersion: version,
    confirmedVersion: null,
    busy: false,
  }
}

export function versionConfirmed(state: PolicyDraft, version: number): PolicyDraft {
  if (state.savedVersion !== version) {
    return { ...state, busy: false }
  }
  return { ...state, confirmedVersion: version, busy: false }
}

export function rememberActive(state: PolicyDraft, version: number | null, checksum: string | null): PolicyDraft {
  return { ...state, activeVersion: version, activeChecksum: checksum }
}

export function activationConflict(
  state: PolicyDraft,
  activeVersion: number | null,
  activeChecksum: string | null,
): PolicyDraft {
  return {
    ...state,
    activeVersion,
    activeChecksum,
    confirmedVersion: null,
    busy: false,
    conflictMessage: "La versión activa cambió. Revisa la comparación antes de volver a intentar.",
  }
}

export function activationAccepted(state: PolicyDraft, version: number, checksum: string): PolicyDraft {
  return {
    ...state,
    activeVersion: version,
    activeChecksum: checksum,
    confirmedVersion: version,
    busy: false,
    conflictMessage: null,
  }

}

export function applyRemoteFailure(state: PolicyDraft, status: number, details: FieldError[] = []): RemoteOutcome {
  if (status === 422) {
    return {
      state: validationRejected(state, details.length > 0 ? details : [{ field: "$", code: "POLICY_INVALID" }]),
      message: "La validación no pasó. El borrador sigue editable y la versión activa no cambió.",
      refreshActive: false,
    }
  }
  if (status === 409) {
    return {
      state: { ...state, busy: false, confirmedVersion: null },
      message: "La versión activa cambió. Hay que volver a leerla antes de activar.",
      refreshActive: true,
    }
  }
  if (status === 401 || status === 403) {
    return {
      state: { ...state, busy: false, accessDenied: true },
      message: status === 401 ? "Se requiere una sesión." : "Permiso insuficiente para esta operación.",
      refreshActive: false,
    }
  }
  return {
    state: { ...state, busy: false },
    message: "El servicio no completó la operación. El borrador y la versión activa se conservan.",
    refreshActive: false,
  }
}

export function canActivate(state: PolicyDraft, isAdmin: boolean): boolean {
  return (
    isAdmin &&
    !state.accessDenied &&
    !state.busy &&
    state.conflictMessage == null &&
    state.errors.length === 0 &&
    state.validatedSource != null &&
    state.validatedSource === state.draftSource &&
    state.normalizedText != null &&
    state.savedVersion != null &&
    state.confirmedVersion === state.savedVersion
  )
}

export function readRules(document: unknown): RuleView[] {
  if (document == null || typeof document !== "object" || !("rules" in document)) {
    return []
  }
  const rules = document.rules
  if (!Array.isArray(rules)) {
    return []
  }
  return rules.flatMap((rule) => {
    if (rule == null || typeof rule !== "object") {
      return []
    }
    const item = rule as Record<string, unknown>
    if (typeof item.id !== "string" || typeof item.effect !== "string") {
      return []
    }
    return [
      {
        id: item.id,
        effect: item.effect,
        tools: stringList(item.tools),
        resources: stringList(item.resources),
      },
    ]
  })
}

export function semanticDiff(activeRules: RuleView[], candidateRules: RuleView[]): SemanticDiff {
  const active = new Map(activeRules.map((rule) => [rule.id, JSON.stringify(rule)]))
  const candidate = new Map(candidateRules.map((rule) => [rule.id, JSON.stringify(rule)]))
  return {
    added: candidateRules.filter((rule) => !active.has(rule.id)).map((rule) => rule.id),
    removed: activeRules.filter((rule) => !candidate.has(rule.id)).map((rule) => rule.id),
    changed: candidateRules
      .filter((rule) => active.has(rule.id) && active.get(rule.id) !== candidate.get(rule.id))
      .map((rule) => rule.id),
  }
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === "string")
}
