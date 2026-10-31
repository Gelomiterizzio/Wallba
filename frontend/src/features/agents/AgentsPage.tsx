import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router-dom"
import type { AgentPage } from "../../api/types"
import { useAuthedApi } from "../../app/session"
import { EmptyState, ErrorPanel, LoadingState, PageHeader, TableScroll } from "../../components/states"

export function AgentsPage() {
  const { client, keys } = useAuthedApi()
  const [search, setSearch] = useState("")
  const query = useQuery({
    queryKey: keys.agents(),
    queryFn: ({ signal }) => client.get<AgentPage>("/agents", { limit: 100 }, signal),
  })
  const term = search.trim().toLowerCase()
  const items = (query.data?.items ?? []).filter(
    (agent) => agent.id.toLowerCase().includes(term) || agent.name.toLowerCase().includes(term),
  )

  return (
    <>
      <PageHeader title="Agentes" description="Capacidades declaradas por el servidor. Este listado no cambia privilegios." />
      <div className="filter-grid">
        <div className="field">
          <label htmlFor="agent-search">Buscar por nombre o ID</label>
          <input id="agent-search" type="search" value={search} onChange={(event) => setSearch(event.target.value)} />
        </div>
      </div>
      {query.isPending ? <LoadingState label="Cargando agentes" /> : null}
      {query.isError ? <ErrorPanel error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.isSuccess && items.length === 0 ? (
        <EmptyState title={term ? "Ningún agente coincide con la búsqueda" : "No hay agentes registrados"}>
          {term ? (
            <button type="button" className="button" onClick={() => setSearch("")}>
              Limpiar búsqueda
            </button>
          ) : null}
        </EmptyState>
      ) : null}
      {items.length > 0 ? (
        <TableScroll label="Agentes registrados">
          <table>
            <caption>Agentes registrados</caption>
            <thead>
              <tr>
                <th scope="col">Nombre</th>
                <th scope="col">ID</th>
                <th scope="col">Estado</th>
                <th scope="col">Herramientas declaradas</th>
              </tr>
            </thead>
            <tbody>
              {items.map((agent) => (
                <tr key={agent.id}>
                  <td>
                    <Link to={`/agents/${encodeURIComponent(agent.id)}`}>{agent.name}</Link>
                  </td>
                  <td className="mono">{agent.id}</td>
                  <td>{agent.status === "ACTIVE" ? "Activo" : "Deshabilitado"}</td>
                  <td>
                    <ul className="tag-list">
                      {agent.tools.map((tool) => (
                        <li key={tool}>{tool}</li>
                      ))}
                    </ul>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      ) : null}
    </>
  )
}
