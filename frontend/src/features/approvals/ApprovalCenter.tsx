import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react"
import { ApprovalRequestError, createApprovalApi } from "./api"
import type { ApprovalAction, ApprovalApi, ApprovalDetail, ApprovalFilters, ApprovalStatus, Identity, Risk } from "./types"
import "./approvals.css"

const STATUS: Record<ApprovalStatus, string> = {
  PENDING: "Pendiente", APPROVED: "Aprobada", CONSUMED: "Consumida", REJECTED: "Rechazada", EXPIRED: "Expirada", CANCELLED: "Cancelada",
}
const ACTION: Record<ApprovalAction, string> = { approve: "Aprobar", reject: "Rechazar", cancel: "Cancelar solicitud" }
const DEFAULT_FILTERS: ApprovalFilters = { status: "PENDING", agent_id: "", risk: "", limit: 25 }
const POLL_MS = 5000

export interface ApprovalCenterProps { client?: ApprovalApi; apiBase?: string }

/** Persona 3 feature. P4 can mount it inside any shell; no fake data is generated. */
export function ApprovalCenter({ client, apiBase = "/api/v1" }: ApprovalCenterProps) {
  const api = useMemo(() => client ?? createApprovalApi(apiBase), [client, apiBase])
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [filters, setFilters] = useState<ApprovalFilters>(DEFAULT_FILTERS)
  const [draftAgent, setDraftAgent] = useState("")
  const [items, setItems] = useState<ApprovalDetail[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<ApprovalDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [asOf, setAsOf] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [action, setAction] = useState<ApprovalAction | null>(null)
  const [confirmedSnapshot, setConfirmedSnapshot] = useState<ApprovalDetail | null>(null)
  const [reason, setReason] = useState("")
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const mounted = useRef(true)
  const sending = useRef(false)
  const requestEpoch = useRef(0)
  const reasonRef = useRef<HTMLTextAreaElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const returnFocus = useRef<HTMLElement | null>(null)
  const listTitle = useId()
  const detailTitle = useId()
  const reasonId = useId()
  const formErrorId = useId()
  const dialogTitle = useId()
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), [])

  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])

  useEffect(() => {
    const controller = new AbortController()
    const epoch = ++requestEpoch.current
    let timer: ReturnType<typeof setTimeout> | undefined
    let inFlight = false
    let stopped = false
    setLoading(true)
    if (!selected) setDetail(null)

    async function load() {
      if (stopped || inFlight || sending.current || document.visibilityState === "hidden") return
      inFlight = true
      try {
        const [session, page, current] = await Promise.all([
          api.me(controller.signal), api.list(filters, controller.signal),
          selected ? api.detail(selected, controller.signal) : Promise.resolve(null),
        ])
        if (stopped || controller.signal.aborted || epoch !== requestEpoch.current) return
        setIdentity(session)
        setItems(page.items)
        setNextCursor(page.next_cursor)
        setDetail(current)
        setAsOf(new Date().toISOString())
        setError(null)
      } catch (failure) {
        if (stopped || controller.signal.aborted || epoch !== requestEpoch.current) return
        setError(readError(failure))
        if (failure instanceof ApprovalRequestError && failure.status === 401) {
          setIdentity(null); setItems([]); setDetail(null)
        }
      } finally {
        inFlight = false
        if (!stopped) { setLoading(false); timer = setTimeout(load, POLL_MS) }
      }
    }
    function visibility() {
      clearTimeout(timer)
      if (document.visibilityState !== "hidden") void load()
    }
    void load()
    document.addEventListener("visibilitychange", visibility)
    return () => { stopped = true; controller.abort(); clearTimeout(timer); document.removeEventListener("visibilitychange", visibility) }
  }, [api, filters, selected, refreshKey])

  useEffect(() => {
    if (action) reasonRef.current?.focus()
    else returnFocus.current?.focus()
  }, [action])

  function openAction(next: ApprovalAction) {
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setReason(""); setFormError(null); setConfirmedSnapshot(detail); setAction(next)
  }

  async function submit() {
    const trimmed = reason.trim()
    if (!confirmedSnapshot || !action || sending.current) return
    if (!trimmed || trimmed.length > 500) { setFormError("Escribe un motivo de entre 1 y 500 caracteres."); reasonRef.current?.focus(); return }
    sending.current = true; setSubmitting(true); setFormError(null); setNotice(null)
    ++requestEpoch.current // A read started before this decision cannot overwrite its result.
    try {
      const session = await api.me()
      if (!mounted.current) return
      setIdentity(session)
      if (identity && session.principal_id !== identity.principal_id) {
        setItems([]); setDetail(null); setSelected(null)
        throw new ApprovalRequestError(409, "SESSION_CHANGED")
      }
      const updated = await api.decide(confirmedSnapshot.approval_id, action, confirmedSnapshot.row_version, trimmed, session.csrf_token)
      if (!mounted.current) return
      setDetail(updated)
      setNotice(`Respuesta confirmada: ${statusLabel(updated.status)}. Ejecución: ${updated.request_state}.`)
      setAction(null)
    } catch (failure) {
      if (!mounted.current) return
      setAction(null)
      setError(readError(failure))
      if (failure instanceof ApprovalRequestError && [409, 410].includes(failure.status)) {
        setNotice("La solicitud cambió o venció. Se actualizarán sus datos; no se repitió la decisión.")
      } else {
        setNotice("La decisión no está confirmada. Consulta el estado antes de realizar otra acción; no se reenvió automáticamente.")
      }
    } finally {
      sending.current = false
      if (mounted.current) { setSubmitting(false); refresh() }
    }
  }

  const pending = detail?.approval_id === selected && detail.status === "PENDING" && detail.request_state !== "UNKNOWN"
  const expired = detail ? Date.parse(detail.expires_at) <= Date.now() : false
  const mayDecide = !!identity?.roles.includes("approver") && identity.principal_id !== detail?.principal_id
  const mayCancel = !!identity && (identity.roles.includes("approver") ||
    (identity.roles.includes("operator") && identity.principal_id === detail?.principal_id))

  return <section className="p3-approvals" aria-label="Persona 3: centro de aprobaciones">
    <header className="p3-approvals__header">
      <div><p className="p3-approvals__eyebrow">WALLBA · Persona 3</p><h1>Aprobaciones humanas</h1>
        <p>Revisa la solicitud exacta antes de autorizar un único intento de ejecución.</p></div>
      <button type="button" onClick={refresh} disabled={loading || submitting}>Actualizar</button>
    </header>
    <p className="p3-approvals__session">{identity ? `Sesión: ${identity.username} · ${identity.roles.join(", ")}` : "Sesión humana no confirmada"}</p>
    <form className="p3-approvals__filters" onSubmit={(event) => { event.preventDefault(); setFilters((value) => ({ ...value, agent_id: draftAgent.trim(), cursor: undefined })); setSelected(null) }}>
      <label>Estado<select value={filters.status} onChange={(event) => { setFilters((value) => ({ ...value, status: event.target.value as ApprovalStatus | "", cursor: undefined })); setSelected(null) }}>
        <option value="">Todos</option>{Object.entries(STATUS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>Agente<input maxLength={64} value={draftAgent} onChange={(event) => setDraftAgent(event.target.value)} placeholder="ID del agente" /></label>
      <label>Riesgo<select value={filters.risk} onChange={(event) => { setFilters((value) => ({ ...value, risk: event.target.value as Risk | "", cursor: undefined })); setSelected(null) }}>
        <option value="">Todos</option>{["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((risk) => <option key={risk}>{risk}</option>)}
      </select></label>
      <button type="submit" disabled={submitting}>Aplicar filtros</button>
      <button type="button" onClick={() => { setFilters(DEFAULT_FILTERS); setDraftAgent(""); setSelected(null) }} disabled={submitting}>Restablecer</button>
    </form>
    {error && <div role="alert" className="p3-approvals__error">{error}</div>}
    {notice && <p role="status" className="p3-approvals__notice">{notice}</p>}
    <p className="p3-approvals__timestamp">{asOf ? `Última lectura: ${formatUtc(asOf)}${error ? " · Datos anteriores" : ""}` : "Sin lectura confirmada"}</p>
    <div className="p3-approvals__layout" aria-busy={loading}>
      <section aria-labelledby={listTitle}>
        <h2 id={listTitle}>Solicitudes</h2>
        {loading && <p role="status">Cargando aprobaciones…</p>}
        {!loading && items.length === 0 && <p>No hay solicitudes para estos filtros.</p>}
        {items.length > 0 && <div className="p3-approvals__table-wrap"><table><caption className="p3-approvals__sr-only">Aprobaciones recibidas del servidor</caption>
          <thead><tr><th scope="col">Solicitud</th><th scope="col">Estado</th><th scope="col">Riesgo</th><th scope="col">Vence (UTC)</th></tr></thead>
          <tbody>{items.map((item) => <tr key={item.approval_id} data-selected={selected === item.approval_id}>
            <td><button className="p3-approvals__link" type="button" aria-pressed={selected === item.approval_id}
              onClick={() => { if (selected !== item.approval_id) { setDetail(null); setSelected(item.approval_id) } else refresh(); setNotice(null) }} disabled={submitting}><span className="p3-approvals__sr-only">Ver solicitud </span>{item.snapshot.call.tool}<small> {item.agent_id}</small><small> {item.request_id}</small></button></td>
            <td><StatusBadge status={item.status} /></td><td>{item.risk}</td><td>{formatUtc(item.expires_at)}</td>
          </tr>)}</tbody>
        </table></div>}
        <nav aria-label="Páginas de aprobaciones" className="p3-approvals__pagination">
          {filters.cursor && <button type="button" onClick={() => { setFilters((value) => ({ ...value, cursor: undefined })); setSelected(null) }} disabled={loading || submitting}>Primera página</button>}
          <button type="button" onClick={() => { setFilters((value) => ({ ...value, cursor: nextCursor ?? undefined })); setSelected(null) }} disabled={!nextCursor || loading || submitting}>Siguiente página</button>
        </nav>
      </section>
      <section className="p3-approvals__detail" aria-labelledby={detailTitle}>
        <h2 id={detailTitle}>Detalle de la solicitud</h2>
        {!selected && <p>Selecciona una solicitud para inspeccionar sus parámetros y permisos.</p>}
        {selected && !detail && <p>Consultando el detalle…</p>}
        {detail && <>
          <StatusBadge status={detail.status} />
          <dl><dt>Solicitud</dt><dd>{detail.request_id}</dd><dt>Agente</dt><dd>{detail.agent_id}</dd>
            <dt>Solicitante</dt><dd>{detail.principal_id}</dd><dt>Herramienta</dt><dd>{detail.snapshot.call.tool}</dd>
            <dt>Recurso</dt><dd>{detail.snapshot.call.resource_id}</dd><dt>Riesgo</dt><dd>{detail.risk}</dd>
            <dt>Política</dt><dd>{detail.policy_id} · versión {detail.policy_version}</dd>
            <dt>Entorno</dt><dd>{detail.snapshot.environment_id}</dd><dt>Versión del recurso</dt><dd>{detail.snapshot.resource_version}</dd>
            <dt>Vencimiento UTC</dt><dd>{formatUtc(detail.expires_at)}</dd><dt>Digest exacto</dt><dd className="p3-approvals__digest">{detail.request_digest}</dd>
            <dt>Estado de ejecución</dt><dd>{detail.request_state}</dd></dl>
          <h3>Parámetros recibidos</h3><pre tabIndex={0} aria-label="Parámetros de la solicitud">{JSON.stringify(detail.snapshot.call.parameters, null, 2)}</pre>
          <p>La decisión se vincula a estos parámetros. Para modificarlos se necesita una solicitud nueva.</p>
          {detail.request_state === "UNKNOWN" && <p role="status" className="p3-approvals__notice">Resultado desconocido. No vuelvas a ejecutar la operación; consulta su evidencia y reconciliación.</p>}
          {detail.receipt && <p>Recibo: <code>{detail.receipt.execution_id}</code> · {detail.receipt.state} · efectos: {detail.receipt.effect_count ?? "no confirmados"} · evidencia: <code>{detail.receipt.evidence_id}</code></p>}
          {expired && detail.status === "PENDING" && <p>El tiempo mostrado ha vencido. El servidor confirma el vencimiento al actuar.</p>}
          <div className="p3-approvals__actions">
            {pending && !expired && mayDecide && <><button type="button" onClick={() => openAction("approve")} disabled={submitting}>Aprobar</button>
              <button type="button" onClick={() => openAction("reject")} disabled={submitting}>Rechazar</button></>}
            {pending && !expired && mayCancel && <button type="button" onClick={() => openAction("cancel")} disabled={submitting}>Cancelar solicitud</button>}
          </div>
          {pending && !mayDecide && <p>La aprobación requiere un humano con rol approver distinto del solicitante. La API vuelve a comprobar los permisos.</p>}
        </>}
      </section>
    </div>
    {action && confirmedSnapshot && <div className="p3-approvals__overlay"><div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={dialogTitle} className="p3-approvals__dialog"
      onKeyDown={(event) => {
        if (event.key === "Escape" && !submitting) { event.preventDefault(); setAction(null) }
        if (event.key === "Tab") {
          const controls = dialogRef.current?.querySelectorAll<HTMLElement>("textarea:not(:disabled),button:not(:disabled)")
          if (!controls?.length) return
          const first = controls[0]; const last = controls[controls.length - 1]
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
        }
      }}>
      <h2 id={dialogTitle}>{ACTION[action]}</h2><p>Solicitud <code>{confirmedSnapshot.request_id}</code>. Riesgo {confirmedSnapshot.risk}. Se enviará la versión {confirmedSnapshot.row_version} que estás revisando.</p>
      <form onSubmit={(event) => { event.preventDefault(); void submit() }}>
        <label htmlFor={reasonId}>Motivo de la decisión</label><textarea id={reasonId} ref={reasonRef} value={reason} maxLength={500} rows={4}
          onChange={(event) => setReason(event.target.value)} aria-invalid={!!formError} aria-describedby={formError ? formErrorId : undefined} disabled={submitting} />
        {formError && <p id={formErrorId} role="alert">{formError}</p>}
        <p>{reason.length}/500 caracteres</p><div className="p3-approvals__actions">
          <button type="submit" disabled={submitting}>{submitting ? "Enviando decisión…" : "Confirmar decisión"}</button>
          <button type="button" onClick={() => setAction(null)} disabled={submitting}>Volver al detalle</button></div>
      </form>
    </div></div>}
  </section>
}

function StatusBadge({ status }: { status: string }) { return <span className="p3-approvals__badge" data-status={status}>{statusLabel(status)}</span> }
function statusLabel(status: string) { return STATUS[status as ApprovalStatus] ?? `Estado desconocido: ${status}` }
function formatUtc(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? "Fecha no disponible" : date.toISOString().replace("T", " ").replace(".000Z", " UTC") }
function readError(error: unknown) {
  if (error instanceof ApprovalRequestError) {
    if (error.code === "SESSION_CHANGED") return "La identidad activa cambió. Actualiza y revisa la solicitud desde la sesión actual."
    const messages: Record<number, string> = {
      401: "La sesión no es válida. Inicia sesión y actualiza esta vista.",
      403: "No tienes permiso para esta acción o la protección de sesión fue rechazada.",
      404: "La solicitud no está disponible para esta identidad.",
      409: "La solicitud cambió o ya fue consumida.", 410: "La aprobación ha vencido.",
      422: "Los datos enviados no cumplen el contrato.", 503: "El servicio no está disponible. No se confirmó la operación.",
    }
    return `${messages[error.status] ?? "No se pudo completar la solicitud."}${error.requestId ? ` Referencia: ${error.requestId}.` : ""}`
  }
  return "No se pudo contactar con WALLBA. Los resultados de una decisión pueden ser inciertos."
}

export default ApprovalCenter
