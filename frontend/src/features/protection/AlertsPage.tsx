import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuthedApi } from "../../app/session"
import { ErrorPanel, LoadingState, PageHeader, formatUtc } from "../../components/states"

const STORAGE = "wallba.guard.project"

type GuardEvent = {
  id: string
  occurred_at: string
  severity: string
  relative_path: string
  operation: string
  outcome: string
  origin_detail: string
  explanation: string
  action_taken: string
  preventive: boolean
}

export function AlertsPage() {
  const { client } = useAuthedApi()
  const queryClient = useQueryClient()
  const [projectId] = useState<string | null>(() => sessionStorage.getItem(STORAGE))
  const [path, setPath] = useState("")
  const [operation, setOperation] = useState("read")
  const [apply, setApply] = useState(false)
  const events = useQuery({
    queryKey: ["guard", "events", projectId],
    enabled: projectId != null,
    queryFn: ({ signal }) => client.get<{ events: GuardEvent[] }>(`/guard/projects/${projectId}/events`, undefined, signal),
  })
  const probe = useMutation({
    mutationFn: () =>
      client.post(`/guard/projects/${projectId}/probe`, {
        relative_path: path,
        operation,
        apply,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["guard", "events", projectId] })
    },
  })
  const watch = useMutation({
    mutationFn: () => client.post(`/guard/projects/${projectId}/watch`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["guard"] })
    },
  })

  return (
    <>
      <PageHeader
        title="Alertas"
        description="Un evento detectado ocurrió antes de registrarse. Solo el agente de prueba puede quedar bloqueado de antemano."
      />
      {projectId == null ? (
        <p>
          Abre un proyecto en <Link to="/protection">Protección</Link>.
        </p>
      ) : null}
      {events.isPending && projectId ? <LoadingState label="Cargando alertas" /> : null}
      {events.isError ? <ErrorPanel error={events.error} onRetry={() => void events.refetch()} /> : null}
      {events.data && events.data.events.length === 0 ? <p>No hay eventos para este proyecto.</p> : null}
      {events.data && events.data.events.length > 0 ? (
        <div className="table-scroll">
          <table>
            <caption>Eventos del guardia</caption>
            <thead>
              <tr>
                <th>Cuándo</th>
                <th>Ruta</th>
                <th>Operación</th>
                <th>Resultado</th>
                <th>Origen</th>
              </tr>
            </thead>
            <tbody>
              {events.data.events.map((event) => (
                <tr key={event.id}>
                  <td>{formatUtc(event.occurred_at)}</td>
                  <td className="mono">{event.relative_path}</td>
                  <td>{event.operation}</td>
                  <td>{event.outcome}{event.preventive ? " · preventiva" : ""}</td>
                  <td>{event.origin_detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {events.data?.events[0] ? (
        <section className="panel">
          <h2 className="panel-title">Detalle del evento más reciente</h2>
          <p>{events.data.events[0].explanation}</p>
          <p className="meta">{events.data.events[0].action_taken}</p>
        </section>
      ) : null}
      {projectId ? (
        <form
          className="panel"
          onSubmit={(event) => {
            event.preventDefault()
            probe.mutate()
          }}
        >
          <h2 className="panel-title">Agente de prueba</h2>
          <p className="meta">Esta acción la ejecuta wallba-test-agent. No atribuye el cambio a otro programa.</p>
          <div className="filter-grid">
            <div className="field">
              <label htmlFor="probe-path">Ruta interna</label>
              <input id="probe-path" value={path} onChange={(event) => setPath(event.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="probe-operation">Operación</label>
              <select id="probe-operation" value={operation} onChange={(event) => setOperation(event.target.value)}>
                <option value="read">Lectura</option>
                <option value="write">Escritura</option>
                <option value="delete">Eliminación</option>
              </select>
            </div>
          </div>
          <label className="check-field">
            <input type="checkbox" checked={apply} onChange={(event) => setApply(event.target.checked)} />
            Aplicar la escritura o eliminación si la política no la deniega
          </label>
          <div className="row">
            <button type="submit" className="button button-primary" disabled={probe.isPending}>
              Comprobar con el agente de prueba
            </button>
            <button type="button" className="button" disabled={watch.isPending} onClick={() => watch.mutate()}>
              Revisar cambios ahora
            </button>
          </div>
        </form>
      ) : null}
      {probe.isError ? <ErrorPanel error={probe.error} /> : null}
      {probe.data ? <p aria-live="polite">Resultado: {String((probe.data as { outcome?: string }).outcome ?? "")}</p> : null}
    </>
  )
}
