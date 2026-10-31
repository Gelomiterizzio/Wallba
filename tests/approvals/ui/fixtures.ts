import type { ApprovalApi, ApprovalDetail, Identity } from "../../../frontend/src/features/approvals/types"
import { vi } from "vitest"

export const identity: Identity = {
  principal_id: "human-reviewer", username: "reviewer", kind: "human", roles: ["viewer", "approver"], csrf_token: "fixture-csrf",
}
export const pending: ApprovalDetail = {
  approval_id: "approval-one", request_id: "request-one", status: "PENDING", row_version: 1,
  created_at: "2026-10-31T12:00:00Z", expires_at: "2099-10-31T12:05:00Z", agent_id: "demo-agent",
  principal_id: "agent-principal", policy_id: "demo-policy", policy_version: 1,
  request_digest: "a".repeat(64), risk: "HIGH", request_state: "PENDING_APPROVAL", receipt: null,
  snapshot: { principal_id: "agent-principal", environment_id: "protected-fixture", resource_version: 1,
    call: { request_id: "request-one", agent_id: "demo-agent", tool: "email.send", operation: "send",
      resource_id: "mailbox:demo-outbox", parameters: { to: "reviewer@example.test", subject: "Demo", body: "Contenido sintético" } } },
}

export function fakeApi(item: ApprovalDetail = pending, session: Identity = identity) {
  let stored = structuredClone(item)
  const api: ApprovalApi = {
    me: vi.fn(async () => session),
    list: vi.fn(async () => ({ items: [stored], next_cursor: null })),
    detail: vi.fn(async () => stored),
    decide: vi.fn(async (_id, action) => {
      stored = { ...stored, row_version: stored.row_version + 1,
        status: action === "approve" ? "CONSUMED" : action === "reject" ? "REJECTED" : "CANCELLED",
        request_state: action === "approve" ? "SUCCEEDED" : action === "reject" ? "REJECTED" : "CANCELLED" }
      return stored
    }),
  }
  return api
}
