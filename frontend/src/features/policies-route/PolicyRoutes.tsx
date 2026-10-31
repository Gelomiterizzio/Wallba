/** Enruta las pantallas de P2 por sus exports, sin editar su lógica. */
import { useMemo } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useSession } from "../../app/session"
import { usesExampleData } from "../../components/ExampleBanner"
import { createPolicyApi, PolicyEditorPage, PolicyListPage } from "../policies"

function usePolicyClient() {
  const { session } = useSession()
  const csrf = session?.csrf_token ?? null
  return useMemo(() => createPolicyApi("/api/v1", csrf), [csrf])
}

export function PolicyListRoute() {
  const client = usePolicyClient()
  const navigate = useNavigate()
  const { session } = useSession()
  return (
    <PolicyListPage
      client={client}
      canEdit={Boolean(session?.roles.includes("policy_admin"))}
      exampleData={usesExampleData()}
      onEdit={(policyId) => navigate(`/policies/${encodeURIComponent(policyId)}/edit`)}
    />
  )
}

export function PolicyEditorRoute() {
  const client = usePolicyClient()
  const { policyId = "" } = useParams()
  const { session } = useSession()
  return (
    <PolicyEditorPage
      client={client}
      policyId={policyId}
      canAdmin={Boolean(session?.roles.includes("policy_admin"))}
      exampleData={usesExampleData()}
    />
  )
}
