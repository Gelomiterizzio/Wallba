import { useQuery } from "@tanstack/react-query"
import type { QueryParams } from "../../api/client"
import type { AuditDetail, AuditPage } from "../../api/types"
import { useAuthedApi } from "../../app/session"

/** Filtros permitidos en la URL. No incluye nada sensible: solo IDs, códigos y fechas. */
export const AUDIT_FILTER_NAMES = [
  "tool",
  "decision",
  "risk",
  "event_type",
  "agent_id",
  "request_id",
  "run_id",
  "q",
  "from",
  "to",
] as const

export type AuditFilterName = (typeof AUDIT_FILTER_NAMES)[number]
export type AuditFilterValues = Partial<Record<AuditFilterName, string>>

export function readFilters(params: URLSearchParams): AuditFilterValues {
  const filters: AuditFilterValues = {}
  for (const name of AUDIT_FILTER_NAMES) {
    const value = params.get(name)
    if (value) {
      filters[name] = value
    }
  }
  return filters
}

export function useAuditPage(filters: AuditFilterValues, cursor: string | null) {
  const { client, keys } = useAuthedApi()
  const params: QueryParams = { ...filters, cursor, limit: 50 }
  return useQuery({
    queryKey: keys.audit(params),
    queryFn: ({ signal }) => client.get<AuditPage>("/audit", params, signal),
    // Al paginar se mantiene la tabla anterior hasta tener la siguiente.
    placeholderData: (previous) => previous,
  })
}

export function useAuditEvent(eventId: string) {
  const { client, keys } = useAuthedApi()
  return useQuery({
    queryKey: keys.auditEvent(eventId),
    queryFn: ({ signal }) => client.get<AuditDetail>(`/audit/${encodeURIComponent(eventId)}`, undefined, signal),
  })
}

export function useTimeline(filters: { request_id?: string | null; run_id?: string | null }) {
  const { client, keys } = useAuthedApi()
  const params: QueryParams = { ...filters, limit: 100 }
  return useQuery({
    queryKey: keys.timeline(params),
    enabled: Boolean(filters.request_id || filters.run_id),
    queryFn: ({ signal }) => client.get<AuditPage>("/audit", params, signal),
    select: (page) => [...page.items].sort((left, right) => left.sequence - right.sequence),
  })
}
