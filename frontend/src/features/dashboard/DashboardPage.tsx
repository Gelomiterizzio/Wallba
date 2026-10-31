import { useMemo } from "react"
import { Link, useSearchParams } from "react-router-dom"
import type { AuditEvent } from "../../api/types"
import { DecisionBadge, RiskBadge } from "../../components/badges"
import { EmptyState, ErrorPanel, formatUtc, LoadingState, PageHeader, shortId, TableScroll } from "../../components/states"
import { GuardSummary } from "../protection/GuardSummary"
import { useDashboard, windowStart, WINDOWS, type WindowKey } from "./dashboardQueries"

const DECISION_LABELS = { ALLOW: "Permitido", DENY: "Denegado", REQUIRE_APPROVAL: "Requiere aprobación" }
const RISK_LABELS = { LOW: "Bajo", MEDIUM: "Medio", HIGH: "Alto", CRITICAL: "Crítico" }

function isWindow(value: string | null): value is WindowKey {
  return value !== null && value in WINDOWS
}

export function DashboardPage() {
  const [params, setParams] = useSearchParams()
  const rawWindow = params.get("window")
  const windowKey: WindowKey = isWindow(rawWindow) ? rawWindow : "all"
  const includeBaseline = params.get("baseline") === "true"
  // El inicio del rango se fija al elegirlo: no cambia en cada render.
  const from = useMemo(() => windowStart(windowKey, Date.now()), [windowKey])
  const query = useDashboard(from, includeBaseline)
  const auditLink = (eventType: string) =>
    `/audit?${new URLSearchParams({ event_type: eventType, ...(from ? { from } : {}) }).toString()}`

  function update(name: string, value: string | null) {
    setParams((current) => {
      const next = new URLSearchParams(current)
      if (value) {
        next.set(name, value)
      } else {
        next.delete(name)
      }
      return next
    })
  }

  const data = query.data
  return (
    <>
      <PageHeader title="Dashboard" description="Actividad registrada en la auditoría. Una denegación es una decisión, no un fallo de ejecución.">
        <div className="row">
          <div className="field">
            <label htmlFor="dashboard-window">Periodo</label>
            <select
              id="dashboard-window"
              value={windowKey}
              onChange={(event) => update("window", event.target.value === "all" ? null : event.target.value)}
            >
              {Object.entries(WINDOWS).map(([key, option]) => (
                <option key={key} value={key}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <label className="check-field">
            <input
              type="checkbox"
              checked={includeBaseline}
              onChange={(event) => update("baseline", event.target.checked ? "true" : null)}
            />
            Incluir baseline sin firewall
          </label>
        </div>
      </PageHeader>
      <GuardSummary />

      {query.isPending ? <LoadingState label="Cargando actividad" /> : null}
      {query.isError ? (
        <ErrorPanel error={query.error} title={data ? "No se pudo actualizar; datos anteriores" : undefined} onRetry={() => void query.refetch()} />
      ) : null}

      {data ? (
        <>
          <p className="meta" aria-live="polite">
            Datos al {formatUtc(data.as_of)}
            {query.isFetching ? " · actualizando…" : ""}
            {data.include_baseline ? " · INCLUYE BASELINE SIN FIREWALL" : " · solo entorno protegido"}
          </p>
          <div className="stat-grid">
            <StatCard label="Solicitudes" value={data.counters.requests} to={auditLink("request_received")} />
            <StatCard label="Decisiones" value={data.counters.decisions} to={auditLink("authorization_decided")} />
            <StatCard label="Ejecuciones completadas" value={data.counters.executions_completed} to={auditLink("execution_completed")} />
            <StatCard label="Ejecuciones fallidas" value={data.counters.executions_failed} to={auditLink("execution_failed")} />
            <StatCard label="Resultado incierto" value={data.counters.executions_unknown} to={auditLink("execution_unknown")} />
            <StatCard label="Aprobaciones pendientes" value={data.counters.approvals_pending} to={auditLink("approval_created")} />
          </div>
          <div className="two-columns">
            <Distribution title="Decisiones" counts={data.by_decision} labels={DECISION_LABELS} />
            <Distribution title="Riesgo de las decisiones" counts={data.by_risk} labels={RISK_LABELS} />
          </div>
          <RecentActivity events={data.recent} />
        </>
      ) : null}
    </>
  )
}

function StatCard({ label, value, to }: { label: string; value: number; to: string }) {
  return (
    <Link to={to} className="stat-card" style={{ color: "inherit", textDecoration: "none" }}>
      <span className="stat-value">{value}</span>
      <span className="meta">{label}</span>
    </Link>
  )
}

function Distribution<K extends string>({
  title,
  counts,
  labels,
}: {
  title: string
  counts: Partial<Record<K, number>>
  labels: Record<K, string>
}) {
  const entries = (Object.keys(labels) as K[]).map((key) => ({ key, label: labels[key], value: counts[key] ?? 0 }))
  const total = entries.reduce((sum, entry) => sum + entry.value, 0)
  return (
    <section className="panel" aria-labelledby={`${title}-heading`}>
      <h2 id={`${title}-heading`} className="panel-title">
        {title}
      </h2>
      <ul className="bar-list">
        {entries.map((entry) => (
          <li key={entry.key}>
            <div className="bar-label">
              <span>{entry.label}</span>
              <span>{entry.value}</span>
            </div>
            <div className="bar-track" aria-hidden="true">
              <div className="bar-fill" style={{ width: total ? `${(entry.value / total) * 100}%` : 0 }} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

function RecentActivity({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return (
      <EmptyState title="Sin actividad en este periodo">
        <p>
          Aún no hay eventos. Puedes ejecutar un escenario en el <Link to="/playground">Playground</Link>.
        </p>
      </EmptyState>
    )
  }
  return (
    <TableScroll label="Actividad reciente">
      <table>
        <caption>Actividad reciente</caption>
        <thead>
          <tr>
            <th scope="col">Evento</th>
            <th scope="col">Hora</th>
            <th scope="col">Decisión</th>
            <th scope="col">Riesgo</th>
            <th scope="col">Detalle</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.event_id}>
              <td className="mono">{event.event_type}</td>
              <td>{formatUtc(event.occurred_at)}</td>
              <td>
                <DecisionBadge value={event.decision} />
              </td>
              <td>
                <RiskBadge value={event.risk} />
              </td>
              <td>
                <Link to={`/audit/${event.event_id}`} aria-label={`${shortId(event.event_id)}, abrir evento ${event.sequence}`}>
                  {shortId(event.event_id)}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  )
}
