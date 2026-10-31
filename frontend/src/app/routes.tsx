import { Navigate, Route, Routes } from "react-router-dom"
import { ErrorPanel } from "../components/states"
import { AgentDetails } from "../features/agents/AgentDetails"
import { AgentsPage } from "../features/agents/AgentsPage"
import { ApprovalCenter } from "../features/approvals"
import { AttackMatrixPage } from "../features/attack-matrix/AttackMatrixPage"
import { AuditEventPage } from "../features/audit/AuditEventPage"
import { AuditPage } from "../features/audit/AuditPage"
import { DashboardPage } from "../features/dashboard/DashboardPage"
import { LoginPage } from "../features/login/LoginPage"
import { PlaygroundPage } from "../features/playground/PlaygroundPage"
import { PlaygroundRunPage } from "../features/playground/PlaygroundRunPage"
import { PolicyEditorRoute, PolicyListRoute } from "../features/policies-route/PolicyRoutes"
import { AppShell } from "./AppShell"
import { useSession } from "./session"

export function AppRoutes() {
  const { status, error, retry } = useSession()

  if (status === "loading") {
    return <p className="boot-message" aria-busy="true">Cargando sesión…</p>
  }
  if (status === "unavailable") {
    return (
      <main className="boot-page">
        <h1>WALLBA</h1>
        <ErrorPanel error={error} title="La autenticación no está disponible" onRetry={retry} />
      </main>
    )
  }
  if (status === "anonymous") {
    return <LoginPage />
  }
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="agents" element={<AgentsPage />} />
        <Route path="agents/:agentId" element={<AgentDetails />} />
        <Route path="policies" element={<PolicyListRoute />} />
        <Route path="policies/:policyId/edit" element={<PolicyEditorRoute />} />
        <Route path="approvals" element={<ApprovalCenter />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="audit/:eventId" element={<AuditEventPage />} />
        <Route path="playground" element={<PlaygroundPage />} />
        <Route path="playground/:runId" element={<PlaygroundRunPage />} />
        <Route path="matrix" element={<AttackMatrixPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

function NotFound() {
  return (
    <>
      <h1>Página no encontrada</h1>
      <p>Esta dirección no existe. Usa la navegación para continuar.</p>
    </>
  )
}
