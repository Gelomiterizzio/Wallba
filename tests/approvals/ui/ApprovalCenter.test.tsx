import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import axe from "axe-core"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ApprovalCenter } from "../../../frontend/src/features/approvals/ApprovalCenter"
import { ApprovalRequestError } from "../../../frontend/src/features/approvals/api"
import { fakeApi, identity, pending } from "./fixtures"

async function openDetail() {
  await userEvent.click(await screen.findByRole("button", { name: /Ver solicitud.*request-one/ }))
  await screen.findByText("Parámetros recibidos")
}

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

describe("Persona 3 approval center", () => {
  it("loads real-client values, renders escaped parameters and provides viewer-only inspection", async () => {
    const unsafe = { ...pending, snapshot: { ...pending.snapshot, call: { ...pending.snapshot.call, parameters: { body: "<img src=x onerror=alert(1)>" } } } }
    render(<ApprovalCenter client={fakeApi(unsafe, { ...identity, roles: ["viewer"] })} />)
    expect(screen.getByText("Cargando aprobaciones…")).toBeInTheDocument()
    await openDetail()
    expect(screen.getByLabelText("Parámetros de la solicitud")).toHaveTextContent("<img src=x onerror=alert(1)>")
    expect(document.querySelector("img")).toBeNull()
    expect(screen.queryByRole("button", { name: "Aprobar" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Rechazar" })).not.toBeInTheDocument()
    expect(screen.getByText(/requiere un humano con rol approver/)).toBeInTheDocument()
  })

  it("requires reason, traps focus, confirms once, and returns focus", async () => {
    const api = fakeApi()
    render(<ApprovalCenter client={api} />)
    await openDetail()
    const approve = screen.getByRole("button", { name: "Aprobar" })
    await userEvent.click(approve)
    const dialog = screen.getByRole("dialog", { name: "Aprobar" })
    const input = within(dialog).getByRole("textbox", { name: "Motivo de la decisión" })
    expect(input).toHaveFocus()
    await userEvent.tab({ shift: true })
    expect(within(dialog).getByRole("button", { name: "Volver al detalle" })).toHaveFocus()
    await userEvent.tab()
    expect(input).toHaveFocus()
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirmar decisión" }))
    expect(api.decide).not.toHaveBeenCalled()
    expect(within(dialog).getByRole("alert")).toHaveTextContent("entre 1 y 500")
    await userEvent.type(input, "Operación revisada por humano")
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirmar decisión" }))
    await waitFor(() => expect(api.decide).toHaveBeenCalledTimes(1))
    expect(api.decide).toHaveBeenCalledWith("approval-one", "approve", 1, "Operación revisada por humano", "fixture-csrf")
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(screen.getByText(/Respuesta confirmada/)).toHaveTextContent("SUCCEEDED")
  })

  it("Escape closes a dialog and restores the original trigger", async () => {
    render(<ApprovalCenter client={fakeApi()} />)
    await openDetail()
    const trigger = screen.getByRole("button", { name: "Rechazar" })
    await userEvent.click(trigger)
    await userEvent.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it("refreshes on 409 without retrying a decision", async () => {
    const api = fakeApi()
    vi.mocked(api.decide).mockRejectedValue(new ApprovalRequestError(409, "APPROVAL_ALREADY_CONSUMED", "trace-conflict"))
    render(<ApprovalCenter client={api} />)
    await openDetail()
    await userEvent.click(screen.getByRole("button", { name: "Aprobar" }))
    await userEvent.type(screen.getByLabelText("Motivo de la decisión"), "Revisado")
    await userEvent.click(screen.getByRole("button", { name: "Confirmar decisión" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(api.decide).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/no se repitió la decisión/)).toBeInTheDocument()
    expect(api.detail).toHaveBeenCalledTimes(2)
  })

  it("does not retry a network-ambiguous mutation", async () => {
    const api = fakeApi()
    vi.mocked(api.decide).mockRejectedValue(new TypeError("network"))
    render(<ApprovalCenter client={api} />)
    await openDetail()
    await userEvent.click(screen.getByRole("button", { name: "Aprobar" }))
    await userEvent.type(screen.getByLabelText("Motivo de la decisión"), "Revisado")
    await userEvent.click(screen.getByRole("button", { name: "Confirmar decisión" }))
    await screen.findByText(/no se reenvió automáticamente/)
    expect(api.decide).toHaveBeenCalledTimes(1)
  })

  it("does not submit under a different identity than the one that reviewed the snapshot", async () => {
    const api = fakeApi()
    render(<ApprovalCenter client={api} />)
    await openDetail()
    await userEvent.click(screen.getByRole("button", { name: "Aprobar" }))
    await userEvent.type(screen.getByLabelText("Motivo de la decisión"), "Revisado")
    vi.mocked(api.me).mockResolvedValue({ ...identity, principal_id: "different-human" })
    await userEvent.click(screen.getByRole("button", { name: "Confirmar decisión" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(api.decide).not.toHaveBeenCalled()
  })

  it("locks a pending submission against duplicate clicks", async () => {
    const api = fakeApi()
    let resolve!: (value: typeof pending) => void
    vi.mocked(api.decide).mockImplementation(() => new Promise((done) => { resolve = done }))
    render(<ApprovalCenter client={api} />)
    await openDetail()
    await userEvent.click(screen.getByRole("button", { name: "Aprobar" }))
    await userEvent.type(screen.getByLabelText("Motivo de la decisión"), "Revisado")
    const form = screen.getByLabelText("Motivo de la decisión").closest("form")!
    fireEvent.submit(form)
    fireEvent.submit(form)
    await waitFor(() => expect(api.decide).toHaveBeenCalledTimes(1))
    expect(screen.getByRole("button", { name: "Enviando decisión…" })).toBeDisabled()
    await act(async () => { resolve({ ...pending, status: "CONSUMED", row_version: 2, request_state: "SUCCEEDED" }) })
  })

  it("prevents self approval and allows owner cancellation", async () => {
    render(<ApprovalCenter client={fakeApi({ ...pending, principal_id: identity.principal_id }, { ...identity, roles: ["operator", "approver"] })} />)
    await openDetail()
    expect(screen.queryByRole("button", { name: "Aprobar" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Cancelar solicitud" })).toBeEnabled()
  })

  it("shows UNKNOWN honestly without mutation controls", async () => {
    render(<ApprovalCenter client={fakeApi({ ...pending, request_state: "UNKNOWN" })} />)
    await openDetail()
    expect(screen.getByText(/Resultado desconocido/)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Aprobar" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Cancelar solicitud" })).not.toBeInTheDocument()
  })

  it("shows empty/error states and applies filters and cursor", async () => {
    const api = fakeApi()
    vi.mocked(api.list).mockResolvedValue({ items: [pending], next_cursor: "next-page" })
    render(<ApprovalCenter client={api} />)
    await screen.findByRole("button", { name: /Ver solicitud.*request-one/ })
    await userEvent.click(screen.getByRole("button", { name: "Siguiente página" }))
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: "next-page" }), expect.any(AbortSignal)))
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Estado" }), "EXPIRED")
    await userEvent.type(screen.getByRole("textbox", { name: "Agente" }), "demo-agent")
    vi.mocked(api.list).mockResolvedValue({ items: [], next_cursor: null })
    await userEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }))
    await screen.findByText("No hay solicitudes para estos filtros.")
    expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ status: "EXPIRED", agent_id: "demo-agent", cursor: undefined }), expect.any(AbortSignal))
  })

  it("clears prior data after 401", async () => {
    const api = fakeApi()
    render(<ApprovalCenter client={api} />)
    await openDetail()
    vi.mocked(api.me).mockRejectedValue(new ApprovalRequestError(401, "AUTHENTICATION_REQUIRED"))
    await userEvent.click(screen.getByRole("button", { name: "Actualizar" }))
    await screen.findByRole("alert")
    expect(screen.queryByLabelText("Parámetros de la solicitud")).not.toBeInTheDocument()
    expect(screen.getByText("Sesión humana no confirmada")).toBeInTheDocument()
  })

  it("aborts outstanding reads when unmounted", async () => {
    const api = fakeApi()
    let signal: AbortSignal | undefined
    vi.mocked(api.me).mockImplementation((value) => { signal = value; return new Promise(() => {}) })
    const { unmount } = render(<ApprovalCenter client={api} />)
    expect(signal?.aborted).toBe(false)
    unmount()
    expect(signal?.aborted).toBe(true)
  })

  it("polls at five seconds, pauses while hidden, and stops after unmount", async () => {
    vi.useFakeTimers()
    const api = fakeApi()
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
    const { unmount } = render(<ApprovalCenter client={api} />)
    await act(async () => {})
    expect(api.list).toHaveBeenCalledTimes(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(api.list).toHaveBeenCalledTimes(2)
    visibility.mockReturnValue("hidden")
    fireEvent(document, new Event("visibilitychange"))
    await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
    expect(api.list).toHaveBeenCalledTimes(2)
    visibility.mockReturnValue("visible")
    await act(async () => { fireEvent(document, new Event("visibilitychange")) })
    expect(api.list).toHaveBeenCalledTimes(3)
    unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
    expect(api.list).toHaveBeenCalledTimes(3)
  })

  it("does not overlap slow reads", async () => {
    vi.useFakeTimers()
    const api = fakeApi()
    vi.mocked(api.list).mockImplementation(() => new Promise(() => {}))
    const { unmount } = render(<ApprovalCenter client={api} />)
    await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
    expect(api.list).toHaveBeenCalledTimes(1)
    unmount()
  })

  it("has no serious or critical automated semantic accessibility violations", async () => {
    render(<main><ApprovalCenter client={fakeApi()} /></main>)
    await openDetail()
    await userEvent.click(screen.getByRole("button", { name: "Aprobar" }))
    // These two rules need real canvas/layout; the browser suite covers them.
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false }, "label-content-name-mismatch": { enabled: false } } })
    expect(result.violations.filter((issue) => ["serious", "critical"].includes(issue.impact ?? ""))).toEqual([])
  })
})
