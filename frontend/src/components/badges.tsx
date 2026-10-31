/** Estado siempre con palabra e icono. Un valor no reconocido nunca se presenta como éxito. */

type Tone = "allow" | "deny" | "approval" | "unknown" | "neutral" | "info"
type BadgeSpec = { label: string; tone: Tone; icon: string }

function Badge({ spec }: { spec: BadgeSpec }) {
  return (
    <span className={`badge badge-${spec.tone}`}>
      <span aria-hidden="true">{spec.icon}</span> {spec.label}
    </span>
  )
}

function lookup(table: Record<string, BadgeSpec>, value: string | null | undefined, empty: string): BadgeSpec {
  if (value === null || value === undefined) {
    return { label: empty, tone: "neutral", icon: "–" }
  }
  return table[value] ?? { label: `Estado desconocido (${value})`, tone: "unknown", icon: "?" }
}

const DECISIONS: Record<string, BadgeSpec> = {
  ALLOW: { label: "Permitido", tone: "allow", icon: "✓" },
  DENY: { label: "Denegado", tone: "deny", icon: "✕" },
  REQUIRE_APPROVAL: { label: "Requiere aprobación", tone: "approval", icon: "!" },
}

const RISKS: Record<string, BadgeSpec> = {
  LOW: { label: "Riesgo bajo", tone: "neutral", icon: "▁" },
  MEDIUM: { label: "Riesgo medio", tone: "approval", icon: "▃" },
  HIGH: { label: "Riesgo alto", tone: "deny", icon: "▅" },
  CRITICAL: { label: "Riesgo crítico", tone: "deny", icon: "█" },
}

// "Completado" significa que el run terminó con observaciones, no que algo fuera seguro.
const RUN_STATES: Record<string, BadgeSpec> = {
  RUNNING: { label: "En curso", tone: "info", icon: "…" },
  PENDING: { label: "Pendiente", tone: "info", icon: "…" },
  WAITING_APPROVAL: { label: "Esperando aprobación humana", tone: "approval", icon: "!" },
  WAITING_ADMIN_INPUT: { label: "Esperando paso administrativo", tone: "approval", icon: "!" },
  COMPLETED: { label: "Completado", tone: "neutral", icon: "■" },
  OBSERVED: { label: "Observado", tone: "neutral", icon: "■" },
  INCOMPLETE: { label: "Incompleto", tone: "approval", icon: "◧" },
  UNKNOWN: { label: "Resultado incierto", tone: "unknown", icon: "?" },
  NOT_APPLICABLE: { label: "No aplica", tone: "neutral", icon: "–" },
}

const RECEIPT_STATES: Record<string, BadgeSpec> = {
  SUCCEEDED: { label: "Ejecutado", tone: "neutral", icon: "■" },
  FAILED: { label: "Falló", tone: "deny", icon: "✕" },
  UNKNOWN: { label: "Resultado incierto", tone: "unknown", icon: "?" },
}

export function DecisionBadge({ value }: { value: string | null | undefined }) {
  return <Badge spec={lookup(DECISIONS, value, "Sin decisión")} />
}

export function RiskBadge({ value }: { value: string | null | undefined }) {
  return <Badge spec={lookup(RISKS, value, "Riesgo no indicado")} />
}

export function RunStateBadge({ value }: { value: string | null | undefined }) {
  return <Badge spec={lookup(RUN_STATES, value, "Sin estado")} />
}

export function ReceiptBadge({ value }: { value: string | null | undefined }) {
  return <Badge spec={lookup(RECEIPT_STATES, value, "Sin recibo")} />
}

export function NotExecutedBadge() {
  return <Badge spec={{ label: "No ejecutado", tone: "neutral", icon: "–" }} />
}
