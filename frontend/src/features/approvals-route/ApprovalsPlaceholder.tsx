import { useSearchParams } from "react-router-dom"
import { EmptyState, PageHeader } from "../../components/states"

/** Ruta reservada: el centro de aprobaciones lo entrega P3 en features/approvals/. */
export function ApprovalsPlaceholder() {
  const [params] = useSearchParams()
  const requestId = params.get("request_id")
  return (
    <>
      <PageHeader title="Aprobaciones" description="Las decisiones las toma una persona autorizada, nunca el agente." />
      <EmptyState title="Centro de aprobaciones aún no integrado">
        <p>Esta pantalla depende del módulo de identidad y aprobaciones. No se puede aprobar nada desde aquí.</p>
        {requestId ? (
          <p>
            Solicitud referida: <span className="mono">{requestId}</span>
          </p>
        ) : null}
      </EmptyState>
    </>
  )
}
