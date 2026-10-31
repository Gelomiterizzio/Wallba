import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { ApiRequestError } from "../../api/client"
import type { ScenarioView } from "../../api/types"
import { useAuthedApi } from "../../app/session"
import { RiskBadge } from "../../components/badges"
import { ConfirmDialog } from "../../components/ConfirmDialog"
import { ErrorPanel, LoadingState, PageHeader } from "../../components/states"
import { useScenarios, useStartRun } from "./demoQueries"

const MAX_SEED = 2_147_483_647

export function PlaygroundPage() {
  const { can } = useAuthedApi()
  const navigate = useNavigate()
  const scenarios = useScenarios()
  const start = useStartRun()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [seed, setSeed] = useState("7")
  const [confirming, setConfirming] = useState(false)

  const selected = scenarios.data?.find((scenario) => scenario.id === selectedId) ?? null
  const seedNumber = Number(seed)
  const seedValid = seed !== "" && Number.isInteger(seedNumber) && seedNumber >= 0 && seedNumber <= MAX_SEED
  const canOperate = can("operator")

  function launch() {
    setConfirming(false)
    if (!selected || start.isPending) {
      return
    }
    start.mutate(
      { scenario_id: selected.id, seed: seedNumber },
      { onSuccess: (accepted) => navigate(`/playground/${accepted.run_id}`) },
    )
  }

  return (
    <>
      <PageHeader
        title="Playground"
        description="Compara el mismo intento con y sin firewall sobre dos copias desechables de datos ficticios. El agente es un guion determinista, no un modelo de lenguaje."
      />
      {scenarios.isPending ? <LoadingState label="Cargando escenarios" /> : null}
      {scenarios.isError ? <ErrorPanel error={scenarios.error} onRetry={() => void scenarios.refetch()} /> : null}
      {scenarios.data ? (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            setConfirming(true)
          }}
        >
          <fieldset className="scenario-list">
            <legend className="field-label">Escenario</legend>
            {scenarios.data.map((scenario) => (
              <ScenarioOption
                key={scenario.id}
                scenario={scenario}
                checked={selectedId === scenario.id}
                onSelect={() => setSelectedId(scenario.id)}
              />
            ))}
          </fieldset>
          <div className="filter-grid">
            <div className="field">
              <label htmlFor="seed">Semilla</label>
              <input
                id="seed"
                type="number"
                min={0}
                max={MAX_SEED}
                step={1}
                value={seed}
                aria-invalid={!seedValid}
                aria-describedby="seed-help"
                onChange={(event) => setSeed(event.target.value)}
              />
              <span id="seed-help" className="meta">
                La misma semilla produce las mismas condiciones iniciales.
              </span>
            </div>
          </div>
          {selected ? <ExpectationPanel scenario={selected} /> : null}
          <div className="row">
            <button type="submit" className="button button-primary" disabled={!selected || !seedValid || !canOperate || start.isPending}>
              {start.isPending ? "Iniciando…" : "Ejecutar comparación"}
            </button>
            {!canOperate ? <span className="meta">Se requiere el rol operator; el servidor lo comprueba de nuevo.</span> : null}
          </div>
        </form>
      ) : null}
      {start.isError ? <StartError error={start.error} /> : null}
      <ConfirmDialog
        open={confirming}
        title={`Ejecutar ${selected?.id ?? ""}`}
        confirmLabel="Ejecutar con datos sintéticos"
        onConfirm={launch}
        onCancel={() => setConfirming(false)}
      >
        <p>
          Se crean dos entornos desechables con datos ficticios. Ningún correo sale del sistema y no se toca ningún recurso real.
        </p>
      </ConfirmDialog>
    </>
  )
}

function ScenarioOption({ scenario, checked, onSelect }: { scenario: ScenarioView; checked: boolean; onSelect: () => void }) {
  return (
    <label className="scenario-option">
      <input type="radio" name="scenario" value={scenario.id} checked={checked} onChange={onSelect} />
      <span>
        <strong>
          {scenario.id} · {scenario.title}
        </strong>
        <br />
        <span className="mono meta">{scenario.tool ?? "plano de control"}</span> <RiskBadge value={scenario.risk} />
      </span>
    </label>
  )
}

function ExpectationPanel({ scenario }: { scenario: ScenarioView }) {
  return (
    <div className="panel">
      <h2 className="panel-title">Expectativa de diseño, todavía no es un resultado</h2>
      <dl className="facts">
        <dt>Sin firewall</dt>
        <dd>{scenario.expectation.baseline}</dd>
        <dt>Con firewall</dt>
        <dd>{scenario.expectation.protected}</dd>
      </dl>
    </div>
  )
}

function StartError({ error }: { error: unknown }) {
  if (error instanceof ApiRequestError && error.status === 0) {
    // Inicio ambiguo: el run pudo haber empezado. No se reenvía de forma automática.
    return (
      <div className="panel panel-warning" role="alert">
        <h2 className="panel-title">Resultado pendiente de comprobar</h2>
        <p>
          No llegó respuesta del servidor, así que el run pudo haber empezado o no. Si vuelves a ejecutar y ya existe uno activo, el servidor responderá que hay un conflicto y no se iniciará otro.
        </p>
      </div>
    )
  }
  if (error instanceof ApiRequestError && error.code === "DEMO_ALREADY_ACTIVE") {
    return <ErrorPanel error={error} title="Ya hay un run activo" />
  }
  return <ErrorPanel error={error} title="No se pudo iniciar la comparación" />
}
