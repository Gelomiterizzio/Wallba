import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import type { MatrixPage, MatrixRow, ScenarioView } from "../../api/types"
import { useAuthedApi } from "../../app/session"
import { DecisionBadge, NotExecutedBadge, RiskBadge, RunStateBadge } from "../../components/badges"
import { ErrorPanel, formatUtc, LoadingState, PageHeader, TableScroll } from "../../components/states"
import { useScenarios } from "../playground/demoQueries"

/** Filas del catálogo; un resultado solo aparece si viene de un run persistido. */
export function AttackMatrixPage() {
  const { client, keys } = useAuthedApi()
  const scenarios = useScenarios()
  const matrix = useQuery({
    queryKey: keys.matrix(),
    queryFn: ({ signal }) => client.get<MatrixPage>("/matrix", { limit: 100 }, signal),
  })

  const runsByScenario = new Map<string, MatrixRow[]>()
  for (const row of matrix.data?.items ?? []) {
    runsByScenario.set(row.scenario_id, [...(runsByScenario.get(row.scenario_id) ?? []), row])
  }
  const executed = scenarios.data?.filter((scenario) => runsByScenario.has(scenario.id)).length ?? 0

  return (
    <>
      <PageHeader
        title="Matriz de ataques"
        description="Resultados observados en ejecuciones reales. Un escenario sin ejecutar no se presenta como superado."
      />
      {scenarios.isPending || matrix.isPending ? <LoadingState label="Cargando matriz" /> : null}
      {scenarios.isError ? <ErrorPanel error={scenarios.error} onRetry={() => void scenarios.refetch()} /> : null}
      {matrix.isError ? <ErrorPanel error={matrix.error} onRetry={() => void matrix.refetch()} /> : null}
      {scenarios.data && matrix.data ? (
        <>
          <p className="meta" role="status">
            {executed} de {scenarios.data.length} escenarios con al menos un run persistido.
          </p>
          {executed === 0 ? (
            <p>
              Aún no hay resultados. Ejecuta un escenario en el <Link to="/playground">Playground</Link>.
            </p>
          ) : null}
          <TableScroll label="Matriz de resultados">
            <table>
              <caption>Último run por escenario</caption>
              <thead>
                <tr>
                  <th scope="col">Escenario</th>
                  <th scope="col">Herramienta</th>
                  <th scope="col">Riesgo</th>
                  <th scope="col">Política</th>
                  <th scope="col">Sin firewall</th>
                  <th scope="col">Con firewall</th>
                  <th scope="col">Motivo</th>
                  <th scope="col">Fecha</th>
                  <th scope="col">Evidencia</th>
                </tr>
              </thead>
              <tbody>
                {scenarios.data.map((scenario) => (
                  <ScenarioRow key={scenario.id} scenario={scenario} runs={runsByScenario.get(scenario.id) ?? []} />
                ))}
              </tbody>
            </table>
          </TableScroll>
        </>
      ) : null}
    </>
  )
}

function ScenarioRow({ scenario, runs }: { scenario: ScenarioView; runs: MatrixRow[] }) {
  // La API ordena del más reciente al más antiguo; los anteriores quedan accesibles.
  const [latest, ...older] = runs
  const name = (
    <>
      <strong>{scenario.id}</strong> {scenario.title}
    </>
  )
  if (!latest) {
    return (
      <tr>
        <th scope="row" style={{ whiteSpace: "normal", color: "var(--text)", fontWeight: 400 }}>
          {name}
        </th>
        <td className="mono">{scenario.tool ?? "N/A"}</td>
        <td colSpan={7}>
          <NotExecutedBadge />
        </td>
      </tr>
    )
  }
  return (
    <tr>
      <th scope="row" style={{ whiteSpace: "normal", color: "var(--text)", fontWeight: 400 }}>
        {name}
      </th>
      <td className="mono">{scenario.tool ?? "N/A"}</td>
      <td>
        <RiskBadge value={latest.risk} />
      </td>
      <td className="mono">{latest.policy_id ? `${latest.policy_id} v${latest.policy_version ?? "?"}` : "—"}</td>
      <td>
        <RunStateBadge value={latest.baseline_state} />
        <div className="meta">Efectos: {latest.baseline_effect_count ?? "desconocido"}</div>
      </td>
      <td>
        <RunStateBadge value={latest.protected_state} /> <DecisionBadge value={latest.protected_decision} />
        <div className="meta">Efectos: {latest.protected_effect_count ?? "desconocido"}</div>
      </td>
      <td className="mono">{latest.protected_reason_code ?? "—"}</td>
      <td>{formatUtc(latest.observed_at)}</td>
      <td>
        <Link to={`/playground/${latest.run_id}`} aria-label={`Abrir run de ${scenario.id}`}>
          Abrir run
        </Link>
        {older.length > 0 ? (
          <details>
            <summary>{older.length} anteriores</summary>
            <ul className="side-list">
              {older.map((run) => (
                <li key={run.run_id}>
                  <Link to={`/playground/${run.run_id}`}>{formatUtc(run.observed_at)}</Link>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </td>
    </tr>
  )
}
