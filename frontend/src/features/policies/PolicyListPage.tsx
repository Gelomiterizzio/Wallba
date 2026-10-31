import { useEffect, useState } from "react"
import type { PolicyApi, VersionSummary } from "./policyApi"
import { PolicyRequestError } from "./policyApi"
import "./policies.css"

type PolicyListPageProps = {
  client: PolicyApi
  canEdit: boolean
  exampleData?: boolean
  onEdit: (policyId: string, version: number) => void
}

export function PolicyListPage({ client, canEdit, exampleData = false, onEdit }: PolicyListPageProps) {
  const [items, setItems] = useState<VersionSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    client.list().then(
      (page) => {
        if (active) {
          setItems(page.items)
        }
      },
      (reason: unknown) => {
        if (active) {
          setError(messageFor(reason))
          setItems([])
        }
      },
    )
    return () => {
      active = false
    }
  }, [client])

  return (
    <section className="policy-feature" aria-busy={items == null}>
      <h1>Políticas</h1>
      {exampleData ? <p className="policy-example">DATOS DE EJEMPLO</p> : null}
      {items == null ? <p>Cargando versiones.</p> : null}
      {error ? (
        <p className="policy-error" role="alert">
          {error}
        </p>
      ) : null}
      {items != null && items.length === 0 && error == null ? <p>Todavía no hay versiones guardadas.</p> : null}
      {items != null && items.length > 0 ? (
        <table>
          <caption>Versiones de política</caption>
          <thead>
            <tr>
              <th scope="col">Política</th>
              <th scope="col">Versión</th>
              <th scope="col">Activa</th>
              <th scope="col">Checksum</th>
              <th scope="col">Acción</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.policy_id}-${item.version}`}>
                <td>{item.policy_id}</td>
                <td>{item.version}</td>
                <td>{item.active ? "Activa" : "Histórica"}</td>
                <td>
                  <code>{item.checksum.slice(0, 12)}</code>
                </td>
                <td>
                  <button type="button" onClick={() => onEdit(item.policy_id, item.version)} disabled={!canEdit}>
                    Abrir
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  )
}

function messageFor(reason: unknown): string {
  if (reason instanceof PolicyRequestError) {
    if (reason.status === 401) {
      return "Se requiere una sesión."
    }
    if (reason.status === 403) {
      return "Permiso insuficiente para ver las políticas."
    }
    return `No se pudo cargar la lista. Referencia ${reason.requestId ?? "no disponible"}.`
  }
  return "No se pudo cargar la lista."
}
