/** Toda clave incluye la identidad: dos usuarios nunca comparten una entrada de caché. */
import type { QueryParams } from "./client"

export const sessionKey = ["wallba", "session"] as const

export function queryKeys(identity: string) {
  const root = ["wallba", identity] as const
  return {
    dashboard: (filters: QueryParams) => [...root, "dashboard", filters] as const,
    agents: () => [...root, "agents"] as const,
    agent: (agentId: string) => [...root, "agents", agentId] as const,
    audit: (filters: QueryParams) => [...root, "audit", filters] as const,
    auditEvent: (eventId: string) => [...root, "audit-event", eventId] as const,
    timeline: (filters: QueryParams) => [...root, "timeline", filters] as const,
    scenarios: () => [...root, "scenarios"] as const,
    demoRun: (runId: string) => [...root, "demo-run", runId] as const,
    evidence: (runId: string) => [...root, "evidence", runId] as const,
    matrix: () => [...root, "matrix"] as const,
  }
}
