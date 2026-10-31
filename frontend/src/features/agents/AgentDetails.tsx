import { useQuery } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"
import type { AgentDetail } from "../../api/types"
import { useAuthedApi } from "../../app/session"
import { ErrorPanel, LoadingState, PageHeader } from "../../components/states"

export function AgentDetails() {
  const { agentId = "" } = useParams()
  const { client, keys } = useAuthedApi()
  const query = useQuery({
    queryKey: keys.agent(agentId),
    queryFn: ({ signal }) => client.get<AgentDetail>(`/agents/${encodeURIComponent(agentId)}`, undefined, signal),
  })
  const agent = query.data

  return (
    <>
      <PageHeader title={agent?.name ?? "Agente"} description={agent?.kind_label}>
        <Link to="/agents" className="button link-button">
          Volver a agentes
        </Link>
      </PageHeader>
      {query.isPending ? <LoadingState label="Cargando agente" /> : null}
      {query.isError ? <ErrorPanel error={query.error} onRetry={() => void query.refetch()} /> : null}
      {agent ? (
        <div className="panel">
          <dl className="facts">
            <dt>ID</dt>
            <dd className="mono">{agent.id}</dd>
            <dt>Estado</dt>
            <dd>{agent.status === "ACTIVE" ? "Activo" : "Deshabilitado"}</dd>
            <dt>Herramientas</dt>
            <dd>
              <ul className="tag-list">
                {agent.tools.map((tool) => (
                  <li key={tool}>{tool}</li>
                ))}
              </ul>
            </dd>
            <dt>Recursos en alcance</dt>
            <dd>
              <ul className="tag-list">
                {agent.resource_scopes.map((scope) => (
                  <li key={scope}>{scope}</li>
                ))}
              </ul>
            </dd>
          </dl>
          <p className="meta" style={{ marginTop: 16 }}>
            Estar en alcance no significa estar permitido: cada llamada la decide la política activa.
          </p>
        </div>
      ) : null}
    </>
  )
}
