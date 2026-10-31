import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import type { DemoRun } from "../../api/types"
import { RunStateBadge } from "../../components/badges"
import { ErrorPanel, formatUtc, JsonDetails, LoadingState, PageHeader } from "../../components/states"
import { ComparisonView } from "./ComparisonView"
import { isActiveRun, useDemoRun, useEvidence } from "./demoQueries"

export function PlaygroundRunPage() {
  const { runId = "" } = useParams()
  const query = useDemoRun(runId)
  const run = query.data

  return (
    <>
      <PageHeader title={run ? `Comparación ${run.scenario_id}` : "Comparación"} description={run?.agent_kind_label}>
        <Link to="/playground" className="button link-button">
          Otro escenario
        </Link>
      </PageHeader>
      {query.isPending ? <LoadingState label="Cargando el run" /> : null}
      {query.isError ? (
        <ErrorPanel
          error={query.error}
          title={run ? "No se pudo actualizar; se muestra el último estado conocido" : "No se pudo leer el run"}
          onRetry={() => void query.refetch()}
        />
      ) : null}
      {run ? (
        <>
          <RunSummary run={run} />
          <StatusGuidance run={run} />
          <ComparisonView run={run} />
          <EvidencePanel run={run} />
        </>
      ) : null}
    </>
  )
}

function RunSummary({ run }: { run: DemoRun }) {
  const sameStart =
    run.baseline.before && run.protected.before
      ? run.baseline.before.state_digest === run.protected.before.state_digest
      : null
  return (
    <div className="panel" aria-live="polite">
      <dl className="facts">
        <dt>Estado</dt>
        <dd>
          <RunStateBadge value={run.status} />
        </dd>
        <dt>Run</dt>
        <dd className="mono">{run.run_id}</dd>
        <dt>Semilla</dt>
        <dd className="mono">{run.seed}</dd>
        <dt>Fixture</dt>
        <dd className="mono">{run.fixture_digest ?? "—"}</dd>
        <dt>Estado inicial</dt>
        <dd>
          {sameStart === null ? "Aún sin observar" : sameStart ? "Mismo digest funcional en ambos lados" : "Los digests iniciales NO coinciden"}
        </dd>
        <dt>Inicio</dt>
        <dd>{formatUtc(run.started_at)}</dd>
        <dt>Fin</dt>
        <dd>{formatUtc(run.completed_at)}</dd>
      </dl>
    </div>
  )
}

function StatusGuidance({ run }: { run: DemoRun }) {
  if (run.status === "UNKNOWN") {
    return (
      <div className="panel panel-warning" role="status">
        <h2 className="panel-title">Resultado incierto</h2>
        <p>
          No se pudo demostrar qué ocurrió, así que no se asume que no hubo efecto. Revisa la evidencia y los recibos; no vuelvas a ejecutar para &quot;confirmar&quot;, porque sería otro run distinto.
        </p>
      </div>
    )
  }
  if (run.status === "INCOMPLETE") {
    return (
      <div className="panel panel-warning" role="status">
        <h2 className="panel-title">Run incompleto</h2>
        <p>Falta al menos una observación. Lo observado se conserva y no se completa con la expectativa.</p>
      </div>
    )
  }
  if (run.status === "WAITING_APPROVAL") {
    const request = run.protected.request_ids[0]
    return (
      <div className="panel panel-warning" role="status">
        <h2 className="panel-title">Esperando a una persona</h2>
        <p>El runner nunca aprueba. Debe decidir una persona con rol approver, distinta de quien inició el run.</p>
        <Link to={`/approvals${request ? `?request_id=${request}` : ""}`}>Ir a la solicitud en aprobaciones</Link>
      </div>
    )
  }
  if (run.status === "WAITING_ADMIN_INPUT") {
    return (
      <div className="panel panel-warning" role="status">
        <h2 className="panel-title">Esperando el paso administrativo</h2>
        <p>Una persona con rol policy_admin debe intentar activar la política inválida.</p>
        <Link to="/policies">Ir a políticas</Link>
      </div>
    )
  }
  return null
}

function EvidencePanel({ run }: { run: DemoRun }) {
  const [open, setOpen] = useState(false)
  const hasEvidence = Boolean(run.evidence_id)
  const query = useEvidence(run.run_id, open && hasEvidence)
  if (isActiveRun(run.status) && !hasEvidence) {
    return <p className="meta">La evidencia se genera cuando el run termina.</p>
  }
  if (!hasEvidence) {
    return null
  }
  return (
    <section className="panel" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" className="panel-title">
        Evidencia
      </h2>
      <div className="row">
        <button type="button" className="button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? "Ocultar manifiesto" : "Ver manifiesto"}
        </button>
        <Link to={`/audit?run_id=${run.run_id}`}>Ver eventos de auditoría de este run</Link>
      </div>
      {open && query.isPending ? <LoadingState label="Cargando manifiesto" /> : null}
      {query.isError ? <ErrorPanel error={query.error} onRetry={() => void query.refetch()} /> : null}
      {open && query.data ? (
        <>
          <p className="meta">
            Digest del manifiesto: <span className="mono">{query.data.manifest_digest}</span>
          </p>
          <JsonDetails value={query.data.manifest} summary="Manifiesto completo" />
        </>
      ) : null}
    </section>
  )
}
