/** Public integration surface owned by Persona 3. Server authorization is final. */
export type ApprovalStatus = "PENDING" | "APPROVED" | "CONSUMED" | "REJECTED" | "EXPIRED" | "CANCELLED"
export type Risk = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
export type ApprovalAction = "approve" | "reject" | "cancel"
export type Role = "viewer" | "operator" | "approver" | "policy_admin"

export interface Identity {
  principal_id: string
  username: string
  kind: "human"
  roles: Role[]
  csrf_token: string
}

export interface ToolCall {
  request_id: string
  agent_id: string
  tool: "file.read" | "email.send" | "record.delete" | "db.query"
  operation: "read" | "send" | "delete" | "query"
  resource_id: string
  parameters: Record<string, unknown>
}

export interface ApprovalDetail {
  approval_id: string
  request_id: string
  status: ApprovalStatus
  row_version: number
  expires_at: string
  created_at: string
  agent_id: string
  principal_id: string
  policy_id: string
  policy_version: number
  request_digest: string
  risk: Risk
  snapshot: {
    call: ToolCall
    principal_id: string
    environment_id: string
    resource_version: number
  }
  request_state: string
  receipt: {
    execution_id: string
    state: "SUCCEEDED" | "FAILED" | "UNKNOWN"
    effect_count: number | null
    evidence_id: string
  } | null
}

export interface ApprovalFilters {
  status: ApprovalStatus | ""
  agent_id: string
  risk: Risk | ""
  cursor?: string
  limit: number
}

export interface ApprovalPage {
  items: ApprovalDetail[]
  next_cursor: string | null
}

export interface ApprovalApi {
  me(signal?: AbortSignal): Promise<Identity>
  list(filters: ApprovalFilters, signal?: AbortSignal): Promise<ApprovalPage>
  detail(id: string, signal?: AbortSignal): Promise<ApprovalDetail>
  decide(id: string, action: ApprovalAction, expectedVersion: number, reason: string, csrf: string): Promise<ApprovalDetail>
}
