import { Link, useParams } from "react-router-dom"
import type { AuditEvent } from "../../api/types"
import { DecisionBadge, RiskBadge } from "../../components/badges"
import { ErrorPanel, formatUtc, JsonDetails, LoadingState, PageHeader } from "../../components/states"
import { useAuditEvent, useTimeline } from "./auditQueries"

export function AuditEventPage() {
  const { eventId = "" } = useParams()
  const query = useAuditEvent(eventId)
  const event = query.data?.event
  const integrity = query.data?.integrity

  return (
    <>
      <PageHeader title={event ? `Evento ${event.sequence}` : "Evento"}>
        <Link to="/audit" className="button link-button">
          Volver a auditoría
        </Link>
      </PageHeader>
      {query.isPending ? <LoadingState label="Cargando evento" /> : null}
      {query.isError ? <ErrorPanel error={query.error} onRetry={() => void query.refetch()} /> : null}
      {event && integrity ? (
        <>
          <div className={`panel${integrity.verified ? "" : " panel-error"}`} role={integrity.verified ? undefined : "alert"}>
            <h2 className="panel-title">
              {integrity.verified ? "Cadena verificada hasta este evento" : "La cadena NO se pudo verificar"}
            </h2>
            <p className="meta">
              {integrity.checked_events} eventos comprobados
              {integrity.first_invalid_sequence !== null ? ` · primera secuencia inválida: ${integrity.first_invalid_sequence}` : ""}
            </p>
            <p className="meta">{integrity.limitation}</p>
          </div>
          <div className="panel">
            <EventFacts event={event} />
            <JsonDetails value={event} summary="Ver evento completo" />
          </div>
          <Timeline event={event} />
        </>
      ) : null}
    </>
  )
}

function EventFacts({ event }: { event: AuditEvent }) {
  return (
    <dl className="facts">
      <dt>Tipo</dt>
      <dd className="mono">{event.event_type}</dd>
      <dt>Hora</dt>
      <dd>{formatUtc(event.occurred_at)}</dd>
      <dt>Decisión</dt>
      <dd>
        <DecisionBadge value={event.decision} />
      </dd>
      <dt>Riesgo</dt>
      <dd>
        <RiskBadge value={event.risk} />
      </dd>
      <dt>Motivo</dt>
      <dd className="mono">{event.reason_code ?? "—"}</dd>
      <dt>Herramienta</dt>
      <dd className="mono">{event.tool ?? "—"}</dd>
      <dt>Recurso</dt>
      <dd className="mono">{event.resource_id ?? "—"}</dd>
      <dt>Principal</dt>
      <dd className="mono">{event.principal_id ?? "—"}</dd>
      <dt>Agente</dt>
      <dd className="mono">{event.agent_id ?? "—"}</dd>
      <dt>Entorno</dt>
      <dd className="mono">{event.environment_id ?? "—"}</dd>
      <dt>Política</dt>
      <dd className="mono">{event.policy_id ? `${event.policy_id} v${event.policy_version ?? "?"}` : "—"}</dd>
      <dt>Checksum de política</dt>
      <dd className="mono">{event.checksum ?? "—"}</dd>
      <dt>Solicitud</dt>
      <dd className="mono">{event.request_id ?? "—"}</dd>
      <dt>Run</dt>
      <dd className="mono">{event.run_id ? <Link to={`/playground/${event.run_id}`}>{event.run_id}</Link> : "—"}</dd>
      <dt>Ejecución</dt>
      <dd className="mono">{event.execution_id ?? "—"}</dd>
      <dt>Digest de solicitud</dt>
      <dd className="mono">{event.request_digest ?? "—"}</dd>
      <dt>Hash anterior</dt>
      <dd className="mono">{event.previous_hash}</dd>
      <dt>Hash del evento</dt>
      <dd className="mono">{event.event_hash}</dd>
    </dl>
  )
}

function Timeline({ event }: { event: AuditEvent }) {
  const filters = event.request_id ? { request_id: event.request_id } : { run_id: event.run_id }
  const query = useTimeline(filters)
  if (!event.request_id && !event.run_id) {
    return null
  }
  return (
    <section className="panel" aria-labelledby="timeline-heading">
      <h2 id="timeline-heading" className="panel-title">
        Secuencia correlacionada
      </h2>
      {query.isPending ? <LoadingState label="Cargando secuencia" /> : null}
      {query.isError ? <ErrorPanel error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.data ? (
        <ol className="timeline">
          {query.data.map((item) => (
            <li key={item.event_id} aria-current={item.event_id === event.event_id ? "true" : undefined}>
              <Link to={`/audit/${item.event_id}`} className="mono">
                {item.sequence}. {item.event_type}
              </Link>{" "}
              <DecisionBadge value={item.decision} />
              <div className="meta">
                {formatUtc(item.occurred_at)}
                {item.reason_code ? ` · ${item.reason_code}` : ""}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  )
}
