import { useState, type FormEvent } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { ApiRequestError } from "../../api/client"
import { useAuthedApi } from "../../app/session"
import { DecisionBadge, RiskBadge } from "../../components/badges"
import { EmptyState, ErrorPanel, errorMessage, formatUtc, LoadingState, PageHeader, shortId, TableScroll } from "../../components/states"
import { AUDIT_FILTER_NAMES, readFilters, useAuditPage, type AuditFilterName, type AuditFilterValues } from "./auditQueries"

const TOOLS = ["file.read", "email.send", "record.delete", "db.query"]
const DECISIONS = { ALLOW: "Permitido", DENY: "Denegado", REQUIRE_APPROVAL: "Requiere aprobación" }
const RISKS = { LOW: "Bajo", MEDIUM: "Medio", HIGH: "Alto", CRITICAL: "Crítico" }
const EVENT_TYPES = [
  "request_received",
  "authorization_decided",
  "approval_created",
  "approval_approved",
  "approval_rejected",
  "approval_expired",
  "approval_cancelled",
  "execution_claimed",
  "execution_completed",
  "execution_failed",
  "execution_unknown",
  "policy_activated",
  "demo_started",
  "demo_completed",
]

/** <input type="datetime-local"> usa hora local; la URL y la API viajan en UTC. */
function toLocalInput(value: string | undefined): string {
  if (!value) {
    return ""
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ""
  }
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

function fromLocalInput(value: string): string {
  return value ? new Date(value).toISOString() : ""
}

export function AuditPage() {
  const [params, setParams] = useSearchParams()
  const filters = readFilters(params)
  const cursor = params.get("cursor")
  const query = useAuditPage(filters, cursor)
  const invalidCursor = cursor !== null && query.error instanceof ApiRequestError && query.error.status === 422

  function applyFilters(values: AuditFilterValues) {
    const next = new URLSearchParams()
    for (const name of AUDIT_FILTER_NAMES) {
      const value = values[name]
      if (value) {
        next.set(name, value)
      }
    }
    setParams(next)
  }

  function clearCursor() {
    const next = new URLSearchParams(params)
    next.delete("cursor")
    setParams(next)
  }

  const hasFilters = Object.keys(filters).length > 0
  const items = query.data?.items ?? []

  return (
    <>
      <PageHeader title="Auditoría" description="Eventos registrados en el servidor, sin secretos ni cuerpos de mensajes." />
      {/* La clave reinicia el formulario cuando la URL cambia (atrás, limpiar). */}
      <FilterForm key={params.toString()} filters={filters} onApply={applyFilters} />
      <ExportPanel filters={filters} />

      {query.isPending ? <LoadingState label="Cargando eventos" /> : null}
      {query.isError ? (
        <ErrorPanel
          error={query.error}
          title={invalidCursor ? "La página solicitada ya no es válida" : undefined}
          onRetry={invalidCursor ? undefined : () => void query.refetch()}
          action={
            invalidCursor ? (
              <button type="button" className="button" onClick={clearCursor}>
                Volver a la primera página
              </button>
            ) : undefined
          }
        />
      ) : null}
      {query.isSuccess && items.length === 0 ? (
        <EmptyState title={hasFilters ? "Ningún evento coincide con los filtros" : "Aún no hay eventos registrados"}>
          {hasFilters ? (
            <button type="button" className="button" onClick={() => setParams(new URLSearchParams())}>
              Limpiar filtros
            </button>
          ) : (
            <p>
              Se registran al ejecutar un escenario en el <Link to="/playground">Playground</Link>.
            </p>
          )}
        </EmptyState>
      ) : null}

      {items.length > 0 ? (
        <>
          <TableScroll label="Eventos de auditoría" busy={query.isFetching}>
            <table>
              <caption>Eventos, del más reciente al más antiguo</caption>
              <thead>
                <tr>
                  <th scope="col">Secuencia</th>
                  <th scope="col">Hora</th>
                  <th scope="col">Evento</th>
                  <th scope="col">Decisión</th>
                  <th scope="col">Riesgo</th>
                  <th scope="col">Herramienta</th>
                  <th scope="col">Motivo</th>
                  <th scope="col">Solicitud</th>
                </tr>
              </thead>
              <tbody>
                {items.map((event) => (
                  <tr key={event.event_id}>
                    <td>
                      <Link to={`/audit/${event.event_id}`} aria-label={`Abrir evento ${event.sequence}`}>
                        {event.sequence}
                      </Link>
                    </td>
                    <td>{formatUtc(event.occurred_at)}</td>
                    <td className="mono">{event.event_type}</td>
                    <td>
                      <DecisionBadge value={event.decision} />
                    </td>
                    <td>
                      <RiskBadge value={event.risk} />
                    </td>
                    <td className="mono">{event.tool ?? "—"}</td>
                    <td className="mono">{event.reason_code ?? "—"}</td>
                    <td className="mono">{shortId(event.request_id)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
          <div className="row">
            {cursor ? (
              <button type="button" className="button" onClick={clearCursor}>
                Primera página
              </button>
            ) : null}
            {query.data?.next_cursor ? (
              <button
                type="button"
                className="button"
                onClick={() => {
                  const next = new URLSearchParams(params)
                  next.set("cursor", query.data.next_cursor as string)
                  setParams(next)
                }}
              >
                Eventos anteriores
              </button>
            ) : null}
          </div>
        </>
      ) : null}
    </>
  )
}

function FilterForm({ filters, onApply }: { filters: AuditFilterValues; onApply: (values: AuditFilterValues) => void }) {
  const [draft, setDraft] = useState<AuditFilterValues>(filters)
  const set = (name: AuditFilterName, value: string) => setDraft((current) => ({ ...current, [name]: value }))

  function submit(event: FormEvent) {
    event.preventDefault()
    onApply(draft)
  }

  return (
    <form className="panel" onSubmit={submit} aria-label="Filtros de auditoría">
      <div className="filter-grid">
        <SelectFilter label="Evento" name="event_type" draft={draft} set={set} options={Object.fromEntries(EVENT_TYPES.map((value) => [value, value]))} />
        <SelectFilter label="Decisión" name="decision" draft={draft} set={set} options={DECISIONS} />
        <SelectFilter label="Riesgo" name="risk" draft={draft} set={set} options={RISKS} />
        <SelectFilter label="Herramienta" name="tool" draft={draft} set={set} options={Object.fromEntries(TOOLS.map((value) => [value, value]))} />
        <TextFilter label="Agente" name="agent_id" draft={draft} set={set} />
        <TextFilter label="ID de solicitud" name="request_id" draft={draft} set={set} />
        <TextFilter label="ID de run" name="run_id" draft={draft} set={set} />
        <TextFilter label="Buscar ID o código" name="q" draft={draft} set={set} />
        <div className="field">
          <label htmlFor="filter-from">Desde (tu hora local)</label>
          <input
            id="filter-from"
            type="datetime-local"
            value={toLocalInput(draft.from)}
            onChange={(event) => set("from", fromLocalInput(event.target.value))}
          />
        </div>
        <div className="field">
          <label htmlFor="filter-to">Hasta, sin incluir (tu hora local)</label>
          <input
            id="filter-to"
            type="datetime-local"
            value={toLocalInput(draft.to)}
            onChange={(event) => set("to", fromLocalInput(event.target.value))}
          />
        </div>
      </div>
      <button type="submit" className="button button-primary">
        Aplicar filtros
      </button>
    </form>
  )
}

type FilterProps = {
  label: string
  name: AuditFilterName
  draft: AuditFilterValues
  set: (name: AuditFilterName, value: string) => void
}

function TextFilter({ label, name, draft, set }: FilterProps) {
  return (
    <div className="field">
      <label htmlFor={`filter-${name}`}>{label}</label>
      <input id={`filter-${name}`} value={draft[name] ?? ""} onChange={(event) => set(name, event.target.value.trim())} />
    </div>
  )
}

function SelectFilter({ label, name, draft, set, options }: FilterProps & { options: Record<string, string> }) {
  return (
    <div className="field">
      <label htmlFor={`filter-${name}`}>{label}</label>
      <select id={`filter-${name}`} value={draft[name] ?? ""} onChange={(event) => set(name, event.target.value)}>
        <option value="">Todos</option>
        {Object.entries(options).map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </select>
    </div>
  )
}

function ExportPanel({ filters }: { filters: AuditFilterValues }) {
  const { client } = useAuthedApi()
  const [status, setStatus] = useState("")
  const [error, setError] = useState<unknown>(null)
  const [pending, setPending] = useState(false)
  const ready = Boolean(filters.from && filters.to)

  async function download() {
    setPending(true)
    setError(null)
    setStatus("Preparando la descarga…")
    try {
      const { blob, headers } = await client.download("/audit/export", filters)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = "wallba-audit.jsonl"
      anchor.click()
      URL.revokeObjectURL(url)
      setStatus(
        `Descarga lista: ${headers.get("x-wallba-event-count") ?? "?"} eventos. Digest del manifiesto: ${headers.get("x-wallba-manifest-digest") ?? "no disponible"}`,
      )
    } catch (reason) {
      setError(reason)
      setStatus(errorMessage(reason))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="panel">
      <h2 className="panel-title">Exportar evidencia</h2>
      <p className="meta">
        JSONL saneado con manifiesto, hasta 10 000 eventos. Requiere un rango desde/hasta. La cadena detecta alteraciones, pero quien administra el host podría reescribirla.
      </p>
      <div className="row">
        <button type="button" className="button" disabled={!ready || pending} onClick={() => void download()}>
          Descargar JSONL
        </button>
        {!ready ? <span className="meta">Aplica un rango para habilitar la descarga.</span> : null}
      </div>
      <p className="meta mono" role="status">
        {status}
      </p>
      {error ? <ErrorPanel error={error} title="No se pudo exportar" /> : null}
    </div>
  )
}
