import { useQuery } from "@tanstack/react-query"
import type { Dashboard } from "../../api/types"
import { useAuthedApi } from "../../app/session"

export const WINDOWS = {
  all: { label: "Todo el historial", hours: null },
  "24h": { label: "Últimas 24 horas", hours: 24 },
  "7d": { label: "Últimos 7 días", hours: 24 * 7 },
} as const

export type WindowKey = keyof typeof WINDOWS

export function windowStart(key: WindowKey, now: number): string | undefined {
  const hours = WINDOWS[key].hours
  return hours === null ? undefined : new Date(now - hours * 3_600_000).toISOString()
}

export function useDashboard(from: string | undefined, includeBaseline: boolean) {
  const { client, keys } = useAuthedApi()
  const params = { from, include_baseline: includeBaseline || undefined }
  return useQuery({
    queryKey: keys.dashboard(params),
    queryFn: ({ signal }) => client.get<Dashboard>("/dashboard", params, signal),
  })
}
