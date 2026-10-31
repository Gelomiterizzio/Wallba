import type { ReactNode } from "react"
import { ApiRequestError } from "../api/client"

const STATUS_MESSAGES: Record<number, string> = {
  0: "No se pudo contactar con el servidor. Lo que ves puede estar desactualizado.",
  401: "Tu sesión terminó. Vuelve a iniciar sesión.",
  403: "Tu cuenta no tiene permiso para esta acción.",
  404: "El recurso no existe o no está disponible.",
  409: "El estado cambió en el servidor. Actualiza antes de continuar.",
  413: "La solicitud supera el tamaño permitido.",
  422: "Revisa los datos ingresados.",
  429: "Demasiadas solicitudes. Espera un momento.",
  503: "El servicio no está disponible en este momento.",
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    return STATUS_MESSAGES[error.status] ?? "La operación no se completó."
  }
  return "La operación no se completó."
}

type ErrorPanelProps = {
  error: unknown
  title?: string
  onRetry?: () => void
  action?: ReactNode
}

/** Mensaje seguro y código de correlación. Nunca muestra cuerpos arbitrarios del servidor. */
export function ErrorPanel({ error, title = "No se pudo completar", onRetry, action }: ErrorPanelProps) {
  const known = error instanceof ApiRequestError ? error : null
  return (
    <div className="panel panel-error" role="alert">
      <h2 className="panel-title">{title}</h2>
      <p>{errorMessage(error)}</p>
      {known ? (
        <p className="meta">
          Código <span className="mono">{known.code}</span>
          {known.requestId ? (
            <>
              {" · "}Referencia <span className="mono">{known.requestId}</span>
            </>
          ) : null}
        </p>
      ) : null}
      {known && known.details.length > 0 ? (
        <ul className="meta">
          {known.details.map((detail) => (
            <li key={`${detail.field}-${detail.code}`}>
              <span className="mono">{detail.field}</span>: {detail.code}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="row">
        {onRetry ? (
          <button type="button" className="button" onClick={onRetry}>
            Reintentar lectura
          </button>
        ) : null}
        {action}
      </div>
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="panel panel-empty">
      <h2 className="panel-title">{title}</h2>
      {children}
    </div>
  )
}

/** Conserva el espacio sin mostrar ceros falsos antes de tener respuesta. */
export function LoadingState({ label = "Cargando…" }: { label?: string }) {
  return (
    <div className="skeleton" aria-busy="true" role="status">
      <span className="visually-hidden">{label}</span>
      <div className="skeleton-line" />
      <div className="skeleton-line" />
      <div className="skeleton-line short" />
    </div>
  )
}

export function PageHeader({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {children}
    </div>
  )
}

/** Tabla con scroll horizontal, alcanzable con teclado en pantallas estrechas. */
export function TableScroll({ label, busy, children }: { label: string; busy?: boolean; children: ReactNode }) {
  return (
    <div className="table-scroll" role="region" aria-label={label} aria-busy={busy} tabIndex={0}>
      {children}
    </div>
  )
}

export function JsonDetails({ value, summary = "Ver JSON" }: { value: unknown; summary?: string }) {
  // Como texto en <pre>: un contenido hostil no se interpreta como HTML.
  return (
    <details className="json-details">
      <summary>{summary}</summary>
      <pre className="mono" tabIndex={0}>
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  )
}

export function formatUtc(value: string | null | undefined): string {
  if (!value) {
    return "—"
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  // Hora del navegador con su zona visible; dateStyle no admite timeZoneName.
  return date.toLocaleString("es", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  })
}

export function shortId(value: string | null | undefined): string {
  return value ? `${value.slice(0, 8)}…` : "—"
}
