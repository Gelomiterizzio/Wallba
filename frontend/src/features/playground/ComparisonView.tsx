import { Link } from "react-router-dom"
import type { DemoRun, ResourceSnapshot, SideView } from "../../api/types"
import { DecisionBadge, ReceiptBadge, RiskBadge, RunStateBadge } from "../../components/badges"
import { shortId, TableScroll } from "../../components/states"

/** Muestra lo que reportó el servidor. No recalcula ni infiere ningún resultado. */
export function ComparisonView({ run }: { run: DemoRun }) {
  return (
    <div className="comparison">
      <SideCard title="Sin firewall (baseline aislado)" side={run.baseline} />
      <SideCard title="Con firewall (protegido)" side={run.protected} showApprovals />
    </div>
  )
}

function SideCard({ title, side, showApprovals = false }: { title: string; side: SideView; showApprovals?: boolean }) {
  return (
    <section className="panel" aria-label={title}>
      <h2 className="panel-title">{title}</h2>
      <dl className="facts">
        <dt>Estado</dt>
        <dd>
          <RunStateBadge value={side.state} />
        </dd>
        <dt>Entorno</dt>
        <dd className="mono">{side.environment_id}</dd>
        {side.reason ? (
          <>
            <dt>Motivo</dt>
            <dd>{side.reason}</dd>
          </>
        ) : null}
      </dl>

      <h3 className="field-label" style={{ marginTop: 16 }}>
        Recursos observados
      </h3>
      <SnapshotTable before={side.before} after={side.after} />

      <h3 className="field-label">Decisiones</h3>
      {side.decisions.length === 0 ? (
        <p className="meta">Sin decisiones registradas en este lado.</p>
      ) : (
        <ul className="side-list">
          {side.decisions.map((decision) => (
            <li key={decision.request_id}>
              <DecisionBadge value={decision.decision} /> <RiskBadge value={decision.risk} />
              <div className="meta">
                <span className="mono">{decision.reason_code}</span>
                {decision.policy_id ? ` · ${decision.policy_id} v${decision.policy_version ?? "?"}` : ""}
                {decision.matched_rule_ids.length > 0 ? ` · reglas: ${decision.matched_rule_ids.join(", ")}` : ""}
              </div>
            </li>
          ))}
        </ul>
      )}

      <h3 className="field-label">Ejecuciones</h3>
      {side.receipts.length === 0 ? (
        <p className="meta">Sin recibos de ejecución en este lado.</p>
      ) : (
        <ul className="side-list">
          {side.receipts.map((receipt) => (
            <li key={receipt.execution_id}>
              <ReceiptBadge value={receipt.state} />
              <span className="meta">
                {" "}
                Efectos: {receipt.effect_count ?? "desconocido"} · <span className="mono">{shortId(receipt.execution_id)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}

      {showApprovals && side.approval_ids.length > 0 ? (
        <p>
          <Link to={`/approvals?request_id=${side.request_ids[0] ?? ""}`}>Ver solicitud pendiente</Link>
        </p>
      ) : null}
    </section>
  )
}

function SnapshotTable({ before, after }: { before: ResourceSnapshot | null | undefined; after: ResourceSnapshot | null | undefined }) {
  if (!before && !after) {
    return <p className="meta">Sin observaciones de recursos en este lado.</p>
  }
  const cell = (snapshot: ResourceSnapshot | null | undefined, name: "record_count" | "outbox_count" | "journal_count") =>
    snapshot ? snapshot[name] : "Sin observar"
  return (
    <TableScroll label="Recursos antes y después">
      <table>
        <thead>
          <tr>
            <th scope="col">Recurso</th>
            <th scope="col">Antes</th>
            <th scope="col">Después</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Registros</th>
            <td>{cell(before, "record_count")}</td>
            <td>{cell(after, "record_count")}</td>
          </tr>
          <tr>
            <th scope="row">Correos simulados</th>
            <td>{cell(before, "outbox_count")}</td>
            <td>{cell(after, "outbox_count")}</td>
          </tr>
          <tr>
            <th scope="row">Ejecuciones en el journal</th>
            <td>{cell(before, "journal_count")}</td>
            <td>{cell(after, "journal_count")}</td>
          </tr>
        </tbody>
      </table>
    </TableScroll>
  )
}
