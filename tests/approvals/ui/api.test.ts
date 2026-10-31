import { describe, expect, it, vi } from "vitest"
import { ApprovalRequestError, createApprovalApi } from "../../../frontend/src/features/approvals/api"
import { identity, pending } from "./fixtures"

describe("Persona 3 HTTP client", () => {
  it("encodes filters and includes cookies on reads", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200 }))
    const api = createApprovalApi("/api/v1/", fetcher)
    await api.list({ status: "PENDING", agent_id: "agent/a?b", risk: "HIGH", cursor: "cursor+", limit: 25 })
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain("agent_id=agent%2Fa%3Fb")
    expect(url).toContain("cursor=cursor%2B")
    expect(init.credentials).toBe("include")
    expect(init.cache).toBe("no-store")
  })

  it("posts only captured version and reason, with CSRF, without retries", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify(pending), { status: 200 }))
    const api = createApprovalApi("/api/v1", fetcher)
    await api.decide("id/one", "approve", 3, "Motivo humano", identity.csrf_token)
    expect(fetcher).toHaveBeenCalledTimes(1)
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe("/api/v1/approvals/id%2Fone/approve")
    expect(init.method).toBe("POST")
    expect(init.headers).toMatchObject({ "X-CSRF-Token": identity.csrf_token })
    expect(JSON.parse(String(init.body))).toEqual({ expected_version: 3, reason: "Motivo humano" })
    expect(init.headers).not.toHaveProperty("Origin") // Browser controls Origin.
  })

  it("surfaces conflicts and request id without reflecting server text", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ error: { code: "STALE_POLICY", request_id: "trace-one", message: "secret-not-for-display" } }), { status: 409 }))
    const api = createApprovalApi("/api/v1", fetcher)
    await expect(api.decide("one", "approve", 1, "Razón", "csrf")).rejects.toMatchObject({ status: 409, code: "STALE_POLICY", requestId: "trace-one" })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it("rejects malformed success and permits abort on reads", async () => {
    const fetcher = vi.fn(async () => new Response("not-json", { status: 200 }))
    const controller = new AbortController()
    await expect(createApprovalApi("/api/v1", fetcher).me(controller.signal)).rejects.toBeInstanceOf(ApprovalRequestError)
    expect((fetcher.mock.calls[0] as unknown as [string, RequestInit])[1].signal).toBe(controller.signal)
  })

  it("rejects incomplete lists and nonhuman session responses", async () => {
    const malformed = vi.fn(async () => new Response(JSON.stringify({ items: [{ approval_id: "incomplete" }], next_cursor: null }), { status: 200 }))
    await expect(createApprovalApi("/api/v1", malformed).list({ status: "", agent_id: "", risk: "", limit: 25 })).rejects.toMatchObject({ code: "INVALID_RESPONSE" })
    const agent = vi.fn(async () => new Response(JSON.stringify({ ...identity, kind: "agent" }), { status: 200 }))
    await expect(createApprovalApi("/api/v1", agent).me()).rejects.toMatchObject({ code: "INVALID_RESPONSE" })
  })

  it("rejects a detail whose displayed identifiers disagree with the exact snapshot", async () => {
    const malformed = { ...pending, snapshot: { ...pending.snapshot, call: { ...pending.snapshot.call, request_id: "different-request" } } }
    const fetcher = vi.fn(async () => new Response(JSON.stringify(malformed), { status: 200 }))
    await expect(createApprovalApi("/api/v1", fetcher).detail("approval-one")).rejects.toMatchObject({ code: "INVALID_RESPONSE" })
  })
})
