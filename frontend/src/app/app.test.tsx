import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { fixtures, problem } from "../mocks/handlers"
import { renderApp } from "../test/render"
import { server } from "../test/setup"

const ME = "*/api/v1/auth/me"

describe("shell y sesión", () => {
  it("navega por los siete destinos e identifica la ruta activa", async () => {
    const user = userEvent.setup()
    renderApp()
    const nav = await screen.findByRole("navigation", { name: "Principal" })
    const links = within(nav).getAllByRole("link")
    expect(links.map((link) => link.textContent)).toEqual([
      "Dashboard",
      "Agentes",
      "Políticas",
      "Aprobaciones",
      "Auditoría",
      "Playground",
      "Matriz de ataques",
    ])
    await user.click(within(nav).getByRole("link", { name: "Agentes" }))
    expect(await screen.findByRole("heading", { level: 1, name: "Agentes" })).toBeInTheDocument()
    expect(within(nav).getByRole("link", { name: "Agentes" })).toHaveAttribute("aria-current", "page")
  })

  it("ofrece saltar al contenido, identidad y entorno aislado", async () => {
    renderApp()
    expect(await screen.findByRole("link", { name: "Saltar al contenido" })).toHaveAttribute("href", "#main")
    expect(screen.getByText("DEMO AISLADA")).toBeInTheDocument()
    expect(screen.getByText(fixtures.session.principal_id)).toBeInTheDocument()
  })

  it("sin sesión muestra el login, y un error no revela si la cuenta existe", async () => {
    const user = userEvent.setup()
    server.use(
      http.get(ME, () => problem(401, "UNAUTHENTICATED")),
      http.post("*/api/v1/auth/login", () => problem(401, "UNAUTHENTICATED")),
    )
    renderApp()
    await user.type(await screen.findByLabelText("Usuario"), "alguien")
    await user.type(screen.getByLabelText("Contraseña"), "clave-incorrecta")
    await user.click(screen.getByRole("button", { name: "Iniciar sesión" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Usuario o contraseña incorrectos.")
    expect(screen.getByLabelText("Contraseña")).toHaveValue("")
  })

  it("si la autenticación no existe o falla, lo dice y no muestra datos", async () => {
    server.use(http.get(ME, () => problem(503, "AUTHORIZATION_UNAVAILABLE")))
    renderApp()
    expect(await screen.findByRole("alert")).toHaveTextContent("La autenticación no está disponible")
    expect(screen.queryByRole("navigation", { name: "Principal" })).not.toBeInTheDocument()
  })

  it("al cerrar sesión y entrar otro usuario no quedan datos del anterior", async () => {
    const user = userEvent.setup()
    let identity = fixtures.session
    let loggedIn = true
    const requests: string[] = []
    server.use(
      http.get(ME, () => (loggedIn ? HttpResponse.json(identity) : problem(401, "UNAUTHENTICATED"))),
      http.post("*/api/v1/auth/logout", () => {
        loggedIn = false
        return new HttpResponse(null, { status: 204 })
      }),
      http.post("*/api/v1/auth/login", () => {
        loggedIn = true
        identity = { principal_id: "otra-persona", roles: ["viewer"], csrf_token: "otro" }
        // Igual que el servidor real: el login no devuelve la identidad.
        return HttpResponse.json({ csrf_token: identity.csrf_token, roles: identity.roles })
      }),
      http.get("*/api/v1/agents", () => {
        requests.push(identity.principal_id)
        return HttpResponse.json({ items: fixtures.agents, next_cursor: null })
      }),
    )
    renderApp("/agents")
    expect(await screen.findByText("Agente de demostración")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Cerrar sesión" }))
    await user.type(await screen.findByLabelText("Usuario"), "otra")
    await user.type(screen.getByLabelText("Contraseña"), "clave")
    await user.click(screen.getByRole("button", { name: "Iniciar sesión" }))
    expect(await screen.findByText("otra-persona")).toBeInTheDocument()
    expect(await screen.findByText("Agente de demostración")).toBeInTheDocument()
    // El segundo usuario volvió a consultar: no reutilizó la caché del primero.
    expect(requests).toEqual([fixtures.session.principal_id, "otra-persona"])
  })

  it("una sesión vencida vuelve al acceso y retira las vistas sensibles", async () => {
    const user = userEvent.setup()
    renderApp("/agents")
    await screen.findByText("Agente de demostración")
    server.use(
      http.get("*/api/v1/audit", () => problem(401, "UNAUTHENTICATED")),
      http.get(ME, () => problem(401, "UNAUTHENTICATED")),
    )
    await user.click(screen.getByRole("link", { name: "Auditoría" }))
    expect(await screen.findByLabelText("Usuario")).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText("Agente de demostración")).not.toBeInTheDocument())
  })
})

describe("agentes", () => {
  it("lista lo que dice el servidor y abre el detalle por URL", async () => {
    const user = userEvent.setup()
    renderApp("/agents")
    await user.click(await screen.findByRole("link", { name: "Lector con alcance reducido" }))
    expect(await screen.findByRole("heading", { level: 1, name: "Lector con alcance reducido" })).toBeInTheDocument()
    expect(screen.getByText("file:public-guide")).toBeInTheDocument()
    expect(screen.queryByText("record.delete")).not.toBeInTheDocument()
    expect(screen.getByText(/no significa estar permitido/)).toBeInTheDocument()
  })

  it("una búsqueda sin resultados permite limpiarla", async () => {
    const user = userEvent.setup()
    renderApp("/agents")
    await user.type(await screen.findByLabelText(/Buscar/), "no-existe")
    expect(screen.getByText("Ningún agente coincide con la búsqueda")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Limpiar búsqueda" }))
    expect(screen.getByText("Agente de demostración")).toBeInTheDocument()
  })

  it("no ofrece acciones para cambiar privilegios", async () => {
    renderApp("/agents")
    await screen.findByText("Agente de demostración")
    expect(within(screen.getByRole("main")).queryByRole("button", { name: /editar|eliminar|permiso/i })).not.toBeInTheDocument()
  })

  it("un agente inexistente da un error seguro", async () => {
    renderApp("/agents/no-existe")
    expect(await screen.findByRole("alert")).toHaveTextContent("El recurso no existe")
  })
})

describe("rutas de otros módulos", () => {
  it("monta el listado de políticas de P2 con la marca de ejemplo apagada fuera de modo mock", async () => {
    renderApp("/policies")
    expect(await screen.findByText("demo-policy", { exact: false })).toBeInTheDocument()
  })

  it("monta el centro de aprobaciones de P3 sin datos inventados", async () => {
    renderApp("/approvals")
    expect(await screen.findByRole("heading", { level: 1, name: /Aprobaciones/ })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /^aprobar/i })).not.toBeInTheDocument()
  })

  it("una ruta inexistente mantiene la navegación", async () => {
    renderApp("/no-existe")
    expect(await screen.findByText("Página no encontrada")).toBeInTheDocument()
    expect(screen.getByRole("navigation", { name: "Principal" })).toBeInTheDocument()
  })
})
