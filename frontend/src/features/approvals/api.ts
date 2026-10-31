import type { ApprovalAction, ApprovalApi, ApprovalDetail, ApprovalFilters, ApprovalPage, Identity } from "./types"

export class ApprovalRequestError extends Error {
  constructor(public readonly status: number, public readonly code: string, public readonly requestId?: string) {
    super(code)
    this.name = "ApprovalRequestError"
  }
}

/** Fetch only, without automatic retries or storage of session/CSRF in localStorage. */
export function createApprovalApi(base = "/api/v1", fetcher: typeof fetch = (...args) => fetch(...args)): ApprovalApi {
  const prefix = base.replace(/\/$/, "")
  async function request<T>(path: string, init: RequestInit = {}, valid: (body: unknown) => boolean = isObject): Promise<T> {
    const response = await fetcher(prefix + path, { ...init, credentials: "include", cache: "no-store" })
    const body: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      const envelope = body as { error?: { code?: unknown; request_id?: unknown } } | null
      throw new ApprovalRequestError(response.status,
        typeof envelope?.error?.code === "string" ? envelope.error.code : "REQUEST_FAILED",
        typeof envelope?.error?.request_id === "string" ? envelope.error.request_id : undefined)
    }
    if (!valid(body)) throw new ApprovalRequestError(502, "INVALID_RESPONSE")
    return body as T
  }
  return {
    me: (signal) => request<Identity>("/auth/me", { signal }, isIdentity),
    list: (filters: ApprovalFilters, signal) => {
      const query = new URLSearchParams({ limit: String(filters.limit) })
      for (const field of ["status", "agent_id", "risk", "cursor"] as const) {
        if (filters[field]) query.set(field, filters[field]!)
      }
      return request<ApprovalPage>(`/approvals?${query}`, { signal }, isPage)
    },
    detail: (id, signal) => request<ApprovalDetail>(`/approvals/${encodeURIComponent(id)}`, { signal }, isApproval),
    decide: (id: string, action: ApprovalAction, expectedVersion: number, reason: string, csrf: string) =>
      request<ApprovalDetail>(`/approvals/${encodeURIComponent(id)}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ expected_version: expectedVersion, reason }),
      }, isApproval),
  }
}

function isObject(value: unknown): value is Record<string, unknown> { return !!value && typeof value === "object" && !Array.isArray(value) }
function text(value: unknown, max = 512): value is string { return typeof value === "string" && value.length > 0 && value.length <= max }
function isIdentity(value: unknown) {
  return isObject(value) && value.kind === "human" && text(value.principal_id) && text(value.username) && text(value.csrf_token) &&
    Array.isArray(value.roles) && value.roles.every((role) => ["viewer", "operator", "approver", "policy_admin"].includes(role))
}
function isApproval(value: unknown): boolean {
  if (!isObject(value) || !isObject(value.snapshot) || !isObject(value.snapshot.call)) return false
  const call = value.snapshot.call
  return ["approval_id", "request_id", "status", "agent_id", "principal_id", "policy_id", "request_digest", "request_state"].every((key) => text(value[key])) &&
    Number.isSafeInteger(value.row_version) && Number(value.row_version) >= 1 && Number.isSafeInteger(value.policy_version) && Number(value.policy_version) >= 1 &&
    text(value.expires_at) && Number.isFinite(Date.parse(value.expires_at)) && text(value.created_at) && Number.isFinite(Date.parse(value.created_at)) &&
    /^[0-9a-f]{64}$/.test(String(value.request_digest)) &&
    ["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(String(value.risk)) && value.snapshot.principal_id === value.principal_id && text(value.snapshot.environment_id) &&
    Number.isSafeInteger(value.snapshot.resource_version) && Number(value.snapshot.resource_version) >= 0 &&
    call.request_id === value.request_id && call.agent_id === value.agent_id &&
    ["file.read", "email.send", "record.delete", "db.query"].includes(String(call.tool)) && text(call.operation) && text(call.resource_id) && isObject(call.parameters) &&
    (value.receipt === null || (isObject(value.receipt) && text(value.receipt.execution_id) && text(value.receipt.evidence_id) &&
      ["SUCCEEDED", "FAILED", "UNKNOWN"].includes(String(value.receipt.state)) &&
      (value.receipt.effect_count === null || (Number.isSafeInteger(value.receipt.effect_count) && Number(value.receipt.effect_count) >= 0))))
}
function isPage(value: unknown) { return isObject(value) && Array.isArray(value.items) && value.items.every(isApproval) && (value.next_cursor === null || text(value.next_cursor)) }
