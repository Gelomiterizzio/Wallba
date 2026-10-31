import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { delay, http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { fixtures, problem } from "../../mocks/handlers"
import { renderApp } from "../../test/render"
import { server } from "../../test/setup"
import { isActiveRun, nextPollDelay } from "./demoQueries"

const { S04, S06, UNKNOWN } = fixtures.demoRuns

async function chooseAndConfirm(user: ReturnType<typeof userEvent.setup>, scenario: RegExp) {
  await user.click(await screen.findByRole("radio", { name: scenario }))
  await user.click(screen.getByRole("button", { name: "Ejecutar comparación" }))
  await user.click(await screen.findByRole("button", { name: "Ejecutar con datos sintéticos" }))
}

describe("selección de escenario", () => {
  it("muestra los diez escenarios y rotula la expectativa como no resultado", async () => {
    const user = userEvent.setup()
    renderApp("/playground")
    expect(await screen.findAllByRole("radio")).toHaveLength(10)
    expect(screen.getByRole("button", { name: "Ejecutar comparación" })).toBeDisabled()
    await user.click(screen.getByRole("radio", { name: /S04/ }))
    expect(screen.getByText("Expectativa de diseño, todavía no es un resultado")).toBeInTheDocument()
  })

  it("declara que el agente es un guion, no un modelo", async () => {
    renderApp("/playground")
    expect(await screen.findByText(/guion determinista/)).toBeInTheDocument()
  })

  it("no envía nada sin la confirmación de datos sintéticos", async () => {
    const user = userEvent.setup()
    let posts = 0
    server.use(
      http.post("*/api/v1/demo-runs", () => {
        posts += 1
        return HttpResponse.json({ run_id: S04.run_id, status: "RUNNING" }, { status: 202 })
      }),
    )
    renderApp("/playground")
    await user.click(await screen.findByRole("radio", { name: /S04/ }))
    await user.click(screen.getByRole("button", { name: "Ejecutar comparación" }))
    expect(screen.getByText(/datos ficticios/, { selector: "dialog p" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Cancelar" }))
    expect(posts).toBe(0)
  })

  it("una semilla inválida bloquea el envío", async () => {
    const user = userEvent.setup()
    renderApp("/playground")
    await user.click(await screen.findByRole("radio", { name: /S04/ }))
    const seed = screen.getByLabelText("Semilla")
    await user.clear(seed)
    await user.type(seed, "-5")
    expect(screen.getByRole("button", { name: "Ejecutar comparación" })).toBeDisabled()
  })

  it("sin rol operator explica por qué no puede ejecutar", async () => {
    server.use(http.get("*/api/v1/auth/me", () => HttpResponse.json({ ...fixtures.session, roles: ["viewer"] })))
    const user = userEvent.setup()
    renderApp("/playground")
    await user.click(await screen.findByRole("radio", { name: /S04/ }))
    expect(screen.getByRole("button", { name: "Ejecutar comparación" })).toBeDisabled()
    expect(screen.getByText(/Se requiere el rol operator/)).toBeInTheDocument()
  })
})

describe("inicio del run", () => {
  it("un doble clic envía una sola solicitud con mode paired", async () => {
    const user = userEvent.setup()
    const bodies: unknown[] = []
    server.use(
      http.post("*/api/v1/demo-runs", async ({ request }) => {
        bodies.push(await request.json())
        await delay(30)
        return HttpResponse.json({ run_id: S04.run_id, status: "RUNNING" }, { status: 202 })
      }),
    )
    renderApp("/playground")
    await user.click(await screen.findByRole("radio", { name: /S04/ }))
    await user.click(screen.getByRole("button", { name: "Ejecutar comparación" }))
    await user.dblClick(await screen.findByRole("button", { name: "Ejecutar con datos sintéticos" }))
    await screen.findByRole("heading", { level: 1, name: "Comparación S04" })
    expect(bodies).toEqual([{ scenario_id: "S04", seed: 7, mode: "paired" }])
  })

  it("un 409 avisa del run activo", async () => {
    const user = userEvent.setup()
    server.use(http.post("*/api/v1/demo-runs", () => problem(409, "DEMO_ALREADY_ACTIVE")))
    renderApp("/playground")
    await chooseAndConfirm(user, /S04/)
    expect(await screen.findByRole("alert")).toHaveTextContent("Ya hay un run activo")
  })

  it("sin respuesta no reenvía: queda pendiente de comprobar", async () => {
    const user = userEvent.setup()
    let posts = 0
    server.use(
      http.post("*/api/v1/demo-runs", () => {
        posts += 1
        return HttpResponse.error()
      }),
    )
    renderApp("/playground")
    await chooseAndConfirm(user, /S04/)
    expect(await screen.findByRole("alert")).toHaveTextContent("Resultado pendiente de comprobar")
    await delay(50)
    expect(posts).toBe(1)
  })
})

describe("comparación", () => {
  it("S04: muestra efecto observado sin firewall y DENY sin efecto con firewall", async () => {
    renderApp(`/playground/${S04.run_id}`)
    const baseline = await screen.findByRole("region", { name: /Sin firewall/ })
    const protectedSide = screen.getByRole("region", { name: /Con firewall/ })
    expect(within(baseline).getByRole("row", { name: "Registros 8 7" })).toBeInTheDocument()
    expect(within(protectedSide).getByRole("row", { name: "Registros 8 8" })).toBeInTheDocument()
    expect(within(protectedSide).getByRole("row", { name: "Ejecuciones en el journal 0 0" })).toBeInTheDocument()
    expect(within(protectedSide).getByText(/Denegado/)).toBeInTheDocument()
    expect(within(protectedSide).getByText("Sin recibos de ejecución en este lado.")).toBeInTheDocument()
    expect(screen.getByText("Mismo digest funcional en ambos lados")).toBeInTheDocument()
  })

  it("una recarga de la URL recupera el run persistido", async () => {
    const first = renderApp(`/playground/${S04.run_id}`)
    await screen.findByText(S04.run_id)
    first.unmount()
    renderApp(`/playground/${S04.run_id}`)
    expect(await screen.findByText(S04.run_id)).toBeInTheDocument()
    expect(screen.getByText("Completado")).toBeInTheDocument()
  })

  it("S06 pendiente: no autoaprueba y enlaza a la solicitud exacta", async () => {
    renderApp(`/playground/${S06.run_id}`)
    expect(await screen.findByText("Esperando a una persona")).toBeInTheDocument()
    const link = screen.getByRole("link", { name: "Ir a la solicitud en aprobaciones" })
    expect(link).toHaveAttribute("href", `/approvals?request_id=${S06.protected.request_ids[0]}`)
    expect(screen.queryByRole("button", { name: /aprobar/i })).not.toBeInTheDocument()
    expect(within(screen.getByRole("region", { name: /Con firewall/ })).getByText("Sin recibos de ejecución en este lado.")).toBeInTheDocument()
  })

  it("UNKNOWN: muestra incertidumbre, sin efecto cero ni botón de volver a ejecutar", async () => {
    renderApp(`/playground/${UNKNOWN.run_id}`)
    expect(await screen.findByRole("heading", { name: "Resultado incierto" })).toBeInTheDocument()
    const side = screen.getByRole("region", { name: /Con firewall/ })
    expect(within(side).getByText(/Efectos: desconocido/)).toBeInTheDocument()
    expect(within(side).getAllByText("Sin observar").length).toBeGreaterThan(0)
    expect(screen.queryByRole("button", { name: /ejecutar/i })).not.toBeInTheDocument()
  })

  it("un run incompleto conserva lo observado y lo dice", async () => {
    const partial = {
      ...S04,
      status: "INCOMPLETE",
      evidence_id: null,
      protected: { ...S04.protected, state: "INCOMPLETE", reason: "HARNESS_UNAVAILABLE", decisions: [], after: null },
    }
    server.use(http.get(`*/api/v1/demo-runs/${S04.run_id}`, () => HttpResponse.json(partial)))
    renderApp(`/playground/${S04.run_id}`)
    expect(await screen.findByText("Run incompleto")).toBeInTheDocument()
    expect(screen.getByText("HARNESS_UNAVAILABLE")).toBeInTheDocument()
    const baseline = screen.getByRole("region", { name: /Sin firewall/ })
    expect(within(baseline).getByRole("row", { name: "Registros 8 7" })).toBeInTheDocument()
  })

  it("si los digests iniciales difieren, lo muestra tal cual", async () => {
    const mismatch = {
      ...S04,
      baseline: { ...S04.baseline, before: { ...S04.baseline.before, state_digest: "f".repeat(64) } },
    }
    server.use(http.get(`*/api/v1/demo-runs/${S04.run_id}`, () => HttpResponse.json(mismatch)))
    renderApp(`/playground/${S04.run_id}`)
    expect(await screen.findByText("Los digests iniciales NO coinciden")).toBeInTheDocument()
  })

  it("un run inexistente da error seguro", async () => {
    renderApp("/playground/ffffffff-ffff-4fff-8fff-ffffffffffff")
    expect(await screen.findByRole("alert")).toHaveTextContent("El recurso no existe")
  })

  it("hace polling mientras está activo y se detiene al terminar", async () => {
    const user = userEvent.setup()
    let gets = 0
    server.use(
      http.get(`*/api/v1/demo-runs/${S04.run_id}`, () => {
        gets += 1
        return HttpResponse.json(gets === 1 ? { ...S04, status: "RUNNING", evidence_id: null } : S04)
      }),
    )
    renderApp(`/playground/${S04.run_id}`)
    expect(await screen.findByText("En curso")).toBeInTheDocument()
    expect(await screen.findByText("Completado", {}, { timeout: 4000 })).toBeInTheDocument()
    const settled = gets
    await delay(2300)
    expect(gets).toBe(settled)
    await user.click(screen.getByRole("button", { name: "Ver manifiesto" }))
    expect(await screen.findByText(/Digest del manifiesto/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /eventos de auditoría/ })).toHaveAttribute("href", `/audit?run_id=${S04.run_id}`)
  }, 10000)

  it("el flujo completo va del catálogo al run", async () => {
    const user = userEvent.setup()
    renderApp("/playground")
    await chooseAndConfirm(user, /S04/)
    expect(await screen.findByRole("heading", { level: 1, name: "Comparación S04" })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText("Completado")).toBeInTheDocument(), { timeout: 4000 })
  }, 8000)
})

describe("polling", () => {
  it("se detiene en estados terminales", () => {
    for (const status of ["COMPLETED", "INCOMPLETE", "UNKNOWN"]) {
      expect(nextPollDelay(status, 0)).toBe(false)
      expect(isActiveRun(status)).toBe(false)
    }
  })

  it("sigue cada dos segundos en estados activos, y con backoff limitado tras errores", () => {
    expect(nextPollDelay("WAITING_APPROVAL", 0)).toBe(2000)
    expect(nextPollDelay(undefined, 0)).toBe(2000)
    const delayed = nextPollDelay("RUNNING", 10) as number
    expect(delayed).toBeGreaterThanOrEqual(30_000)
    expect(delayed).toBeLessThan(32_001)
  })
})
