import { http, HttpResponse } from "msw"
import { describe, expect, it, vi } from "vitest"
import { problem } from "../mocks/handlers"
import { server } from "../test/setup"
import { ApiRequestError, buildUrl, createApiClient, readApiError } from "./client"

function client(onUnauthorized = vi.fn()) {
  return createApiClient({ baseUrl: "http://test/api/v1", getCsrfToken: () => "token-csrf", onUnauthorized })
}

describe("cliente HTTP", () => {
  it("envía CSRF y JSON en mutaciones, y no en lecturas", async () => {
    const seen: Headers[] = []
    server.use(
      http.post("http://test/api/v1/x", ({ request }) => {
        seen.push(request.headers)
        return HttpResponse.json({ ok: true })
      }),
      http.get("http://test/api/v1/x", ({ request }) => {
        seen.push(request.headers)
        return HttpResponse.json({ ok: true })
      }),
    )
    await client().post("/x", { a: 1 })
    await client().get("/x")
    expect(seen[0].get("x-csrf-token")).toBe("token-csrf")
    expect(seen[0].get("content-type")).toBe("application/json")
    expect(seen[1].get("x-csrf-token")).toBeNull()
  })

  it("convierte el error común y conserva código y referencia", async () => {
    server.use(http.get("http://test/api/v1/x", () => problem(409, "DEMO_ALREADY_ACTIVE", "Ya existe")))
    const error = await client().get("/x").catch((reason: unknown) => reason)
    expect(error).toBeInstanceOf(ApiRequestError)
    expect(error).toMatchObject({ status: 409, code: "DEMO_ALREADY_ACTIVE" })
    expect((error as ApiRequestError).requestId).toBeTruthy()
  })

  it("avisa al recibir 401 para limpiar la sesión", async () => {
    const onUnauthorized = vi.fn()
    server.use(http.get("http://test/api/v1/x", () => problem(401, "UNAUTHENTICATED")))
    await expect(client(onUnauthorized).get("/x")).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it("distingue el fallo de red con status 0", async () => {
    server.use(http.get("http://test/api/v1/x", () => HttpResponse.error()))
    await expect(client().get("/x")).rejects.toMatchObject({ status: 0, code: "NETWORK_ERROR" })
  })

  it("no expone un cuerpo de error inesperado", () => {
    const error = readApiError(500, "<html>stack trace secreto</html>")
    expect(error.message).not.toContain("secreto")
    expect(error.code).toBe("UNEXPECTED_RESPONSE")
  })

  it("rechaza una respuesta 200 que no es JSON", async () => {
    server.use(http.get("http://test/api/v1/x", () => new HttpResponse("no json", { status: 200 })))
    await expect(client().get("/x")).rejects.toMatchObject({ code: "CONTRACT_ERROR" })
  })

  it("omite parámetros vacíos y escapa los valores", () => {
    expect(buildUrl("/api", "/audit", { a: "", b: null, c: undefined, q: "' OR 1=1" })).toBe("/api/audit?q=%27+OR+1%3D1")
  })
})
