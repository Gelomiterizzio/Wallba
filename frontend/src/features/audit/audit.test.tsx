import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it, vi } from "vitest"
import { fixtures, problem } from "../../mocks/handlers"
import { renderApp } from "../../test/render"
import { server } from "../../test/setup"

const DENIED = fixtures.auditEvents[3]

describe("explorador de auditoría", () => {
  it("una decisión no reconocida no se presenta como éxito", async () => {
    server.use(
      http.get("*/api/v1/audit", () =>
        HttpResponse.json({ items: [{ ...DENIED, decision: "INVENTADA" }], next_cursor: null }),
      ),
    )
    renderApp("/audit")
    expect(await screen.findByText("Estado desconocido (INVENTADA)")).toBeInTheDocument()
    expect(within(screen.getByRole("table")).queryByText(/Permitido/)).not.toBeInTheDocument()
  })

  it("aplica un filtro por request_id desde la URL y solo pide esos eventos", async () => {
    const seen: string[] = []
    server.use(
      http.get("*/api/v1/audit", ({ request }) => {
        seen.push(new URL(request.url).search)
        return HttpResponse.json({ items: [DENIED], next_cursor: null })
      }),
    )
    renderApp(`/audit?request_id=${DENIED.request_id}`)
    expect(await screen.findByLabelText("ID de solicitud")).toHaveValue(DENIED.request_id)
    await waitFor(() => expect(seen[0]).toContain(`request_id=${DENIED.request_id}`))
  })

  it("el formulario actualiza la consulta", async () => {
    const user = userEvent.setup()
    const seen: (string | null)[] = []
    server.use(
      http.get("*/api/v1/audit", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("decision"))
        return HttpResponse.json({ items: [DENIED], next_cursor: null })
      }),
    )
    renderApp("/audit")
    await user.selectOptions(await screen.findByLabelText("Decisión"), "DENY")
    await user.click(screen.getByRole("button", { name: "Aplicar filtros" }))
    await waitFor(() => expect(seen.at(-1)).toBe("DENY"))
  })

  it("distingue vacío inicial de vacío por filtros, y permite limpiar", async () => {
    const user = userEvent.setup()
    server.use(http.get("*/api/v1/audit", () => HttpResponse.json({ items: [], next_cursor: null })))
    renderApp("/audit?decision=DENY")
    expect(await screen.findByText("Ningún evento coincide con los filtros")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }))
    expect(await screen.findByText("Aún no hay eventos registrados")).toBeInTheDocument()
  })

  it("pagina con cursor del servidor", async () => {
    const user = userEvent.setup()
    const cursors: (string | null)[] = []
    server.use(
      http.get("*/api/v1/audit", ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor")
        cursors.push(cursor)
        return HttpResponse.json({ items: [cursor ? fixtures.auditEvents[0] : DENIED], next_cursor: cursor ? null : "Mg==" })
      }),
    )
    renderApp("/audit")
    await user.click(await screen.findByRole("button", { name: "Eventos anteriores" }))
    await waitFor(() => expect(cursors).toContain("Mg=="))
    expect(await screen.findByRole("button", { name: "Primera página" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Eventos anteriores" })).not.toBeInTheDocument()
  })

  it("un cursor inválido ofrece volver a la primera página", async () => {
    const user = userEvent.setup()
    renderApp("/audit?cursor=invalido")
    expect(await screen.findByText("La página solicitada ya no es válida")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Volver a la primera página" }))
    expect(await screen.findAllByText("authorization_decided")).not.toHaveLength(0)
  })

  it("una búsqueda con metacaracteres viaja como texto", async () => {
    let received: string | null = null
    server.use(
      http.get("*/api/v1/audit", ({ request }) => {
        received = new URL(request.url).searchParams.get("q")
        return HttpResponse.json({ items: [], next_cursor: null })
      }),
    )
    renderApp(`/audit?q=${encodeURIComponent("' OR 1=1 --")}`)
    await screen.findByText("Ningún evento coincide con los filtros")
    expect(received).toBe("' OR 1=1 --")
  })

  it("exportar exige un rango", async () => {
    renderApp("/audit")
    expect(await screen.findByRole("button", { name: "Descargar JSONL" })).toBeDisabled()
    expect(screen.getByText(/Aplica un rango/)).toBeInTheDocument()
  })

  it("al terminar la exportación anuncia el resultado con el digest", async () => {
    const user = userEvent.setup()
    URL.createObjectURL = vi.fn(() => "blob:x")
    URL.revokeObjectURL = vi.fn()
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined)
    renderApp(`/audit?from=2026-10-31T00:00:00.000Z&to=2026-11-01T00:00:00.000Z`)
    await user.click(await screen.findByRole("button", { name: "Descargar JSONL" }))
    const region = screen.getAllByRole("status").find((item) => item.className.includes("mono")) as HTMLElement
    await waitFor(() => expect(region).toHaveTextContent(/Descarga lista: 5 eventos.*8888/))
    expect(click).toHaveBeenCalled()
    click.mockRestore()
  })

  it("sin permiso, exportar presenta el error seguro del servidor", async () => {
    const user = userEvent.setup()
    server.use(http.get("*/api/v1/audit/export", () => problem(403, "FORBIDDEN")))
    renderApp(`/audit?from=2026-10-31T00:00:00.000Z&to=2026-11-01T00:00:00.000Z`)
    await user.click(await screen.findByRole("button", { name: "Descargar JSONL" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("no tiene permiso")
  })
})

describe("detalle de evento", () => {
  it("muestra hashes, la limitación de la garantía y la secuencia correlacionada", async () => {
    server.use(
      http.get("*/api/v1/audit", () =>
        HttpResponse.json({ items: [DENIED, fixtures.auditEvents[2]], next_cursor: null }),
      ),
    )
    renderApp(`/audit/${DENIED.event_id}`)
    expect(await screen.findByText("Cadena verificada hasta este evento")).toBeInTheDocument()
    expect(screen.getByText(/administra el host/)).toBeInTheDocument()
    expect(screen.getByText(DENIED.request_digest as string)).toBeInTheDocument()
    const timeline = await screen.findByRole("region", { name: "Secuencia correlacionada" })
    const items = within(timeline).getAllByRole("listitem")
    expect(items.map((item) => within(item).getByRole("link").textContent)).toEqual([
      "3. request_received",
      "4. authorization_decided",
    ])
    expect(items[1]).toHaveAttribute("aria-current", "true")
  })

  it("una cadena alterada se anuncia como alerta", async () => {
    server.use(
      http.get(`*/api/v1/audit/${DENIED.event_id}`, () =>
        HttpResponse.json({
          event: DENIED,
          integrity: { verified: false, checked_events: 1, first_invalid_sequence: 2, limitation: "límite" },
        }),
      ),
    )
    renderApp(`/audit/${DENIED.event_id}`)
    expect(await screen.findByRole("alert")).toHaveTextContent("La cadena NO se pudo verificar")
    expect(screen.queryByText("Cadena verificada hasta este evento")).not.toBeInTheDocument()
  })

  it("un motivo con HTML hostil se muestra como texto y no se ejecuta", async () => {
    const hostile = '<img src=x onerror="window.__xss=1"><script>window.__xss=1</script>'
    server.use(
      http.get(`*/api/v1/audit/${DENIED.event_id}`, () =>
        HttpResponse.json({ event: { ...DENIED, reason_code: hostile }, integrity: fixtures.integrity }),
      ),
    )
    renderApp(`/audit/${DENIED.event_id}`)
    expect(await screen.findByText(hostile)).toBeInTheDocument()
    expect(document.querySelector("img[src='x']")).toBeNull()
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined()
  })

  it("no inventa una solicitud en eventos administrativos", async () => {
    const admin = fixtures.auditEvents[0]
    renderApp(`/audit/${admin.event_id}`)
    await screen.findByText("Cadena verificada hasta este evento")
    expect(screen.queryByRole("region", { name: "Secuencia correlacionada" })).not.toBeInTheDocument()
    expect(screen.getByText(admin.checksum as string)).toBeInTheDocument()
  })
})
