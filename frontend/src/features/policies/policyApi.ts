/** Cliente del contrato /api/v1/policies. No decide autorizaciones. */

import type { FieldError } from "./draftState"

export type VersionSummary = {
  policy_id: string
  version: number
  checksum: string
  active: boolean
  created_at: string
  created_by: string
}

export type VersionDetail = VersionSummary & {
  document: unknown
}

export type PolicyPage = {
  items: VersionSummary[]
  next_cursor: string | null
}

export type ValidateResult = {
  normalized: unknown
}

export class PolicyRequestError extends Error {
  readonly status: number
  readonly code: string
  readonly details: FieldError[]
  readonly requestId: string | null

  constructor(status: number, code: string, details: FieldError[], requestId: string | null) {
    super(code)
    this.name = "PolicyRequestError"
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
  }
}

export type PolicyApi = {
  list(cursor?: string): Promise<PolicyPage>
  getVersion(policyId: string, version: number): Promise<VersionDetail>
  validate(format: "yaml" | "json", content: string): Promise<ValidateResult>
  createVersion(policyId: string, document: unknown): Promise<VersionSummary>
  activate(policyId: string, version: number, expectedActiveVersion: number | null): Promise<VersionSummary>
}

export function readPolicyError(status: number, payload: unknown): PolicyRequestError {
  const error = isRecord(payload) ? payload.error : undefined
  const record = isRecord(error) ? error : {}
  const details = Array.isArray(record.details)
    ? record.details.flatMap((item) => {
        if (!isRecord(item) || typeof item.field !== "string" || typeof item.code !== "string") {
          return []
        }
        return [{ field: item.field, code: item.code }]
      })
    : []
  const code = typeof record.code === "string" ? record.code : "AUTHORIZATION_UNAVAILABLE"
  const requestId = typeof record.request_id === "string" ? record.request_id : null
  return new PolicyRequestError(status, code, details, requestId)
}

export function createPolicyApi(baseUrl: string, csrfToken: string | null = null): PolicyApi {
  const root = baseUrl.replace(/\/$/, "")

  async function request(path: string, init: RequestInit, allow: number[]): Promise<unknown> {
    let response: Response
    try {
      response = await fetch(`${root}${path}`, {
        ...init,
        headers: headers(init, csrfToken),
        credentials: "include",
      })
    } catch {
      throw new PolicyRequestError(0, "AUTHORIZATION_UNAVAILABLE", [], null)
    }
    const payload = await response.json().catch(() => null)
    if (!allow.includes(response.status)) {
      throw readPolicyError(response.status, payload)
    }
    return payload
  }

  return {
    list(cursor?: string) {
      const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""
      return request(`/policies${query}`, { method: "GET" }, [200]) as Promise<PolicyPage>
    },
    getVersion(policyId: string, version: number) {
      return request(`/policies/${encodeURIComponent(policyId)}/versions/${version}`, { method: "GET" }, [200]) as Promise<VersionDetail>
    },
    async validate(format: "yaml" | "json", content: string) {
      const payload = await request(
        "/policies/validate",
        { method: "POST", body: JSON.stringify({ format, content }) },
        [200],
      )
      if (!isRecord(payload) || payload.valid !== true) {
        throw readPolicyError(422, payload)
      }
      return { normalized: payload.normalized_policy }
    },
    createVersion(policyId: string, document: unknown) {
      return request(
        `/policies/${encodeURIComponent(policyId)}/versions`,
        { method: "POST", body: JSON.stringify(document) },
        [201],
      ) as Promise<VersionSummary>
    },
    async activate(policyId: string, version: number, expectedActiveVersion: number | null) {
      const payload = await request(
        `/policies/${encodeURIComponent(policyId)}/activate`,
        { method: "POST", body: JSON.stringify({ version, expected_active_version: expectedActiveVersion }) },
        [200],
      )
      return payload as VersionSummary
    },
  }
}

function headers(init: RequestInit, csrfToken: string | null): Headers {
  const result = new Headers(init.headers)
  result.set("accept", "application/json")
  if (init.body != null) {
    result.set("content-type", "application/json")
  }
  if (csrfToken && init.method !== "GET") {
    result.set("x-csrf-token", csrfToken)
  }
  return result
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object"
}
