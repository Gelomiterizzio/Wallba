import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { useAuthedApi } from "../../app/session"
import { ErrorPanel, LoadingState } from "../../components/states"

type Overview = {
  project: string | null
  summary: {
    files_scanned: number
    directories_scanned: number
    by_risk: Record<string, number>
    events: { blocked: number; observed: number; detected: number }
    rules: number
  } | null
}

export function GuardSummary() {
  const { client } = useAuthedApi()
  const query = useQuery({
    queryKey: ["guard", "overview"],
    queryFn: ({ signal }) => client.get<Overview>("/guard/overview", undefined, signal),
  })
  return (
    <section className="panel" aria-labelledby="guard-summary-title">
      <h2 id="guard-summary-title" className="panel-title">
        Protección de archivos
      </h2>
      {query.isPending ? <LoadingState label="Cargando protección" /> : null}
      {query.isError ? <ErrorPanel error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.data && query.data.summary == null ? (
        <p>
          Ningún proyecto abierto en el guardia. <Link to="/protection">Abrir un proyecto</Link>.
        </p>
      ) : null}
      {query.data?.summary ? (
        <>
          <div className="stat-grid">
            <article className="stat-card">
              <span className="stat-value">{query.data.summary.files_scanned}</span>
              <span className="meta">Archivos examinados</span>
            </article>
            <article className="stat-card">
              <span className="stat-value">{query.data.summary.directories_scanned}</span>
              <span className="meta">Carpetas examinadas</span>
            </article>
            <article className="stat-card">
              <span className="stat-value">{query.data.summary.by_risk.CRITICAL ?? 0}</span>
              <span className="meta">Archivos críticos</span>
            </article>
            <article className="stat-card">
              <span className="stat-value">{query.data.summary.rules}</span>
              <span className="meta">Reglas guardadas</span>
            </article>
            <article className="stat-card">
              <span className="stat-value">{query.data.summary.events.blocked}</span>
              <span className="meta">Operaciones bloqueadas del agente de prueba</span>
            </article>
            <article className="stat-card">
              <span className="stat-value">{query.data.summary.events.detected}</span>
              <span className="meta">Cambios detectados, origen no determinado</span>
            </article>
          </div>
          <p className="meta">
            El bloqueo preventivo aplica solo al agente instrumentado. Un cambio observado después no es un acceso bloqueado.
          </p>
          <Link to="/alerts">Ver alertas</Link>
        </>
      ) : null}
    </section>
  )
}
