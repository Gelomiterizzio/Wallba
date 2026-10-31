/** Alias de los tipos generados desde el contrato. No se definen DTO a mano. */
import type { components } from "./generated"

type Schemas = components["schemas"]

export type AgentSummary = Schemas["AgentSummary"]
export type AgentDetail = Schemas["AgentDetail"]
export type AgentPage = Schemas["Page_AgentSummary_"]
export type AuditEvent = Schemas["AuditEventView"]
export type AuditPage = Schemas["AuditEventPage"]
export type AuditDetail = Schemas["AuditEventDetail"]
export type Dashboard = Schemas["DashboardView"]
export type ScenarioView = Schemas["ScenarioView"]
export type ScenarioPage = Schemas["Page_ScenarioView_"]
export type DemoRun = Schemas["DemoRunView"]
export type DemoRunAccepted = Schemas["DemoRunAccepted"]
export type SideView = Schemas["SideView"]
export type ResourceSnapshot = Schemas["ResourceSnapshot"]
export type Evidence = Schemas["EvidenceView"]
export type MatrixRow = Schemas["MatrixRow"]
export type MatrixPage = Schemas["Page_MatrixRow_"]

/**
 * Identidad que devuelve GET /auth/me. P3 aún no publica este esquema:
 * API_CONTRACTS solo dice "identidad/roles/csrf_token", y estos nombres están por confirmar.
 */
export type Session = {
  principal_id: string
  roles: string[]
  csrf_token: string
}
