import { screen, within } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { fixtures } from "../../mocks/handlers"
import { renderApp } from "../../test/render"
import { server } from "../../test/setup"

function rowFor(id: string) {
  return screen.getByRole("row", { name: new RegExp(`^${id} `) })
}

describe("matriz de ataques", () => {
  it("con diez escenarios y tres runs, siete quedan como No ejecutado", async () => {
    renderApp("/matrix")
    expect(await screen.findByText("3 de 10 escenarios con al menos un run persistido.")).toBeInTheDocument()
    expect(screen.getAllByText("No ejecutado")).toHaveLength(7)
    const row = rowFor("S02")
    expect(within(row).getByText("No ejecutado")).toBeInTheDocument()
    expect(within(row).queryByRole("link")).not.toBeInTheDocument()
  })

  it("sin runs no presenta nada como probado, ni usa las expectativas", async () => {
    server.use(http.get("*/api/v1/matrix", () => HttpResponse.json({ items: [], next_cursor: null })))
    renderApp("/matrix")
    expect(await screen.findByText("0 de 10 escenarios con al menos un run persistido.")).toBeInTheDocument()
    expect(screen.getAllByText("No ejecutado")).toHaveLength(10)
    for (const scenario of fixtures.scenarios) {
      expect(screen.queryByText(scenario.expectation.protected)).not.toBeInTheDocument()
    }
    expect(screen.queryByText("Denegado")).not.toBeInTheDocument()
  })

  it("una fila observada muestra política, decisión, motivo y enlace a su run", async () => {
    renderApp("/matrix")
    await screen.findByText(/escenarios con al menos un run/)
    const row = rowFor("S04")
    expect(within(row).getByText("demo-policy v1")).toBeInTheDocument()
    expect(within(row).getByText(/Denegado/)).toBeInTheDocument()
    expect(within(row).getByText("RULE_DENY")).toBeInTheDocument()
    expect(within(row).getByRole("link", { name: "Abrir run de S04" })).toHaveAttribute(
      "href",
      `/playground/${fixtures.demoRuns.S04.run_id}`,
    )
  })

  it("un run con resultado incierto no parece superado", async () => {
    renderApp("/matrix")
    await screen.findByText(/escenarios con al menos un run/)
    const row = rowFor("S08")
    expect(within(row).getByText("Resultado incierto")).toBeInTheDocument()
    expect(within(row).getByText(/Efectos: desconocido/)).toBeInTheDocument()
  })

  it("conserva runs anteriores sin sobrescribir la historia", async () => {
    const latest = fixtures.matrix[0]
    const older = { ...latest, run_id: "12121212-1212-4212-8212-121212121212", observed_at: "2026-10-30T12:00:00Z" }
    server.use(http.get("*/api/v1/matrix", () => HttpResponse.json({ items: [latest, older], next_cursor: null })))
    renderApp("/matrix")
    await screen.findByText("1 de 10 escenarios con al menos un run persistido.")
    expect(screen.getByText("1 anteriores")).toBeInTheDocument()
    expect(within(rowFor("S04")).getByRole("link", { name: "Abrir run de S04" })).toHaveAttribute(
      "href",
      `/playground/${latest.run_id}`,
    )
  })
})
