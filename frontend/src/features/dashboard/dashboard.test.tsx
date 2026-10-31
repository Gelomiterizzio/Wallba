import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { delay, http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { fixtures, problem } from "../../mocks/handlers"
import { renderApp } from "../../test/render"
import { server } from "../../test/setup"

const EMPTY = {
  ...fixtures.dashboard,
  counters: { events: 0, requests: 0, decisions: 0, executions_completed: 0, executions_failed: 0, executions_unknown: 0, approvals_pending: 0 },
  by_decision: { ALLOW: 0, DENY: 0, REQUIRE_APPROVAL: 0 },
  by_risk: { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 },
  recent: [],
}

function statValue(label: string) {
  return within(screen.getByText(label, { selector: ".meta" }).closest("a") as HTMLElement).getByText(/^\d+$/).textContent
}

describe("dashboard", () => {
  it("con cero eventos muestra ceros reales y un estado vacío", async () => {
    server.use(http.get("*/api/v1/dashboard", () => HttpResponse.json(EMPTY)))
    renderApp()
    expect(await screen.findByText("Sin actividad en este periodo")).toBeInTheDocument()
    expect(statValue("Decisiones")).toBe("0")
    expect(screen.getByText(/Datos al/)).toBeInTheDocument()
  })

  it("mientras carga no muestra ceros falsos", async () => {
    server.use(
      http.get("*/api/v1/dashboard", async () => {
        await delay(50)
        return HttpResponse.json(fixtures.dashboard)
      }),
    )
    renderApp()
    await screen.findByRole("heading", { level: 1, name: "Dashboard" })
    expect(screen.queryByText("Decisiones", { selector: ".meta" })).not.toBeInTheDocument()
    expect(document.querySelector("[aria-busy='true']")).toBeInTheDocument()
    expect(await screen.findByText("Decisiones", { selector: ".meta" })).toBeInTheDocument()
  })

  it("una denegación se cuenta como decisión y no como ejecución fallida", async () => {
    renderApp()
    await screen.findByText("Decisiones", { selector: ".meta" })
    expect(statValue("Decisiones")).toBe("1")
    expect(statValue("Ejecuciones fallidas")).toBe("0")
  })

  it("las tarjetas enlazan a la auditoría filtrada", async () => {
    renderApp()
    const card = (await screen.findByText("Decisiones", { selector: ".meta" })).closest("a")
    expect(card).toHaveAttribute("href", "/audit?event_type=authorization_decided")
  })

  it("la distribución tiene su valor en texto, no solo en la barra", async () => {
    renderApp()
    const section = await screen.findByRole("region", { name: "Decisiones" })
    expect(within(section).getByText("Denegado").parentElement).toHaveTextContent("1")
  })

  it("baseline solo se pide de forma explícita y queda rotulado", async () => {
    const user = userEvent.setup()
    const seen: (string | null)[] = []
    server.use(
      http.get("*/api/v1/dashboard", ({ request }) => {
        const value = new URL(request.url).searchParams.get("include_baseline")
        seen.push(value)
        return HttpResponse.json({ ...fixtures.dashboard, include_baseline: value === "true" })
      }),
    )
    renderApp()
    expect(await screen.findByText(/solo entorno protegido/)).toBeInTheDocument()
    await user.click(screen.getByRole("checkbox", { name: /baseline/ }))
    expect(await screen.findByText(/INCLUYE BASELINE/)).toBeInTheDocument()
    expect(seen).toEqual([null, "true"])
  })

  it("el periodo envía un rango y permanece en la URL", async () => {
    const user = userEvent.setup()
    const seen: (string | null)[] = []
    server.use(
      http.get("*/api/v1/dashboard", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("from"))
        return HttpResponse.json(fixtures.dashboard)
      }),
    )
    renderApp()
    await user.selectOptions(await screen.findByLabelText("Periodo"), "24h")
    await waitFor(() => expect(seen.at(-1)).toMatch(/Z$/))
    expect(seen).toHaveLength(2)
  })

  it("un 503 muestra error con referencia y permite reintentar", async () => {
    const user = userEvent.setup()
    server.use(http.get("*/api/v1/dashboard", () => problem(503, "AUDIT_UNAVAILABLE")))
    renderApp()
    const alert = await screen.findByRole("alert", {}, { timeout: 8000 })
    expect(alert).toHaveTextContent("AUDIT_UNAVAILABLE")
    server.use(http.get("*/api/v1/dashboard", () => HttpResponse.json(fixtures.dashboard)))
    await user.click(screen.getByRole("button", { name: "Reintentar lectura" }))
    expect(await screen.findByText("Decisiones", { selector: ".meta" })).toBeInTheDocument()
  }, 15000)
})
