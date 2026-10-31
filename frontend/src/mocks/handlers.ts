/** Datos de ejemplo para desarrollo y pruebas. pytest valida fixtures.json contra los DTO. */
import { http, HttpResponse, type HttpHandler } from "msw"
import type { AgentDetail, AuditEvent, DemoRun, MatrixRow, ScenarioView, Session } from "../api/types"
import raw from "./fixtures.json"

export const fixtures = raw as unknown as {
  session: Session
  agents: AgentDetail[]
  scenarios: ScenarioView[]
  dashboard: Record<string, unknown>
  auditEvents: AuditEvent[]
  integrity: Record<string, unknown>
  demoRuns: Record<string, DemoRun>
  evidence: Record<string, unknown>
  matrix: MatrixRow[]
  policies: Record<string, unknown>[]
}

const API = "*/api/v1"

export function problem(status: number, code: string, message = "Error de ejemplo") {
  return HttpResponse.json(
    { error: { code, message, request_id: "99999999-9999-4999-8999-999999999999", details: [] } },
    { status },
  )
}

type MockState = { loggedIn: boolean; pendingPolls: Map<string, number>; created: Map<string, DemoRun> }

export function createHandlers(): HttpHandler[] {
  const state: MockState = { loggedIn: true, pendingPolls: new Map(), created: new Map() }
  const allRuns = () => [...Object.values(fixtures.demoRuns), ...state.created.values()]

  return [
    http.get(`${API}/auth/me`, () =>
      state.loggedIn
        ? HttpResponse.json({ ...fixtures.session, kind: "human", username: "mock-operator" })
        : problem(401, "UNAUTHENTICATED"),
    ),
    http.post(`${API}/auth/login`, () => {
      state.loggedIn = true
      return HttpResponse.json(fixtures.session)
    }),
    http.post(`${API}/auth/logout`, () => {
      state.loggedIn = false
      return new HttpResponse(null, { status: 204 })
    }),
    http.get(`${API}/dashboard`, () => HttpResponse.json(fixtures.dashboard)),
    http.get(`${API}/agents`, () => HttpResponse.json({ items: fixtures.agents, next_cursor: null })),
    http.get(`${API}/agents/:agentId`, ({ params }) => {
      const agent = fixtures.agents.find((item) => item.id === params.agentId)
      return agent ? HttpResponse.json(agent) : problem(404, "NOT_FOUND")
    }),
    http.get(`${API}/audit/export`, () => {
      const body = `${fixtures.auditEvents.map((event) => JSON.stringify(event)).join("\n")}\n{"type":"manifest"}\n`
      return new HttpResponse(body, {
        headers: {
          "content-type": "application/x-ndjson",
          "x-wallba-event-count": String(fixtures.auditEvents.length),
          "x-wallba-manifest-digest": "8".repeat(64),
        },
      })
    }),
    http.get(`${API}/audit/:eventId`, ({ params }) => {
      const event = fixtures.auditEvents.find((item) => item.event_id === params.eventId)
      return event ? HttpResponse.json({ event, integrity: fixtures.integrity }) : problem(404, "NOT_FOUND")
    }),
    http.get(`${API}/audit`, ({ request }) => {
      const query = new URL(request.url).searchParams
      if (query.get("cursor") === "invalido") {
        return problem(422, "VALIDATION_ERROR", "Cursor inválido")
      }
      const exact = ["decision", "risk", "tool", "agent_id", "request_id", "run_id", "event_type"] as const
      const items = [...fixtures.auditEvents].reverse().filter((event) =>
        exact.every((name) => !query.get(name) || event[name] === query.get(name)),
      )
      return HttpResponse.json({ items, next_cursor: null })
    }),
    http.get(`${API}/scenarios`, () => HttpResponse.json({ items: fixtures.scenarios, next_cursor: null })),
    http.post(`${API}/demo-runs`, async ({ request }) => {
      const body = (await request.json()) as { scenario_id: string; seed: number }
      const template = fixtures.demoRuns[body.scenario_id]
      const run: DemoRun = template
        ? { ...template, seed: body.seed }
        : {
            ...fixtures.demoRuns.S04,
            run_id: crypto.randomUUID(),
            scenario_id: body.scenario_id as DemoRun["scenario_id"],
            status: "INCOMPLETE",
            evidence_id: null,
            protected: { ...fixtures.demoRuns.S04.protected, state: "INCOMPLETE", reason: "HARNESS_UNAVAILABLE", decisions: [], after: null },
          }
      state.created.set(run.run_id, run)
      state.pendingPolls.set(run.run_id, 1)
      return HttpResponse.json({ run_id: run.run_id, status: "RUNNING" }, { status: 202 })
    }),
    http.get(`${API}/demo-runs/:runId/evidence`, ({ params }) => {
      const run = allRuns().find((item) => item.run_id === params.runId)
      return run?.evidence_id
        ? HttpResponse.json({ ...fixtures.evidence, run_id: run.run_id })
        : problem(404, "NOT_FOUND")
    }),
    http.get(`${API}/demo-runs/:runId`, ({ params }) => {
      const runId = String(params.runId)
      const run = state.created.get(runId) ?? allRuns().find((item) => item.run_id === runId)
      if (!run) {
        return problem(404, "NOT_FOUND")
      }
      const polls = state.pendingPolls.get(runId) ?? 0
      if (polls > 0) {
        state.pendingPolls.set(runId, polls - 1)
        return HttpResponse.json({
          ...run,
          status: "RUNNING",
          evidence_id: null,
          completed_at: null,
          baseline: { ...run.baseline, state: "PENDING", after: null, receipts: [] },
          protected: { ...run.protected, state: "PENDING", after: null, decisions: [], receipts: [] },
        })
      }
      return HttpResponse.json(run)
    }),
    http.get(`${API}/matrix`, () => HttpResponse.json({ items: fixtures.matrix, next_cursor: null })),
    http.get(`${API}/policies`, () => HttpResponse.json({ items: fixtures.policies, next_cursor: null })),
    http.get(`${API}/guard/overview`, () => HttpResponse.json({ project: null, summary: null })),
    http.get(`${API}/approvals`, () => HttpResponse.json({ items: [], next_cursor: null })),
  ]
}
