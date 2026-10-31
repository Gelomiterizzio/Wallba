import { useMutation, useQuery } from "@tanstack/react-query"
import type { DemoRun, DemoRunAccepted, Evidence, ScenarioPage } from "../../api/types"
import { useAuthedApi } from "../../app/session"

const POLL_MS = 2_000
const MAX_BACKOFF_MS = 30_000
const WAITING_STATES = new Set(["RUNNING", "WAITING_APPROVAL", "WAITING_ADMIN_INPUT"])

export function isActiveRun(status: string | undefined): boolean {
  return status !== undefined && WAITING_STATES.has(status)
}

/** Backoff con jitter tras errores; con la pestaña oculta el polling queda en pausa. */
export function nextPollDelay(status: string | undefined, failures: number): number | false {
  if (status !== undefined && !isActiveRun(status)) {
    return false
  }
  if (failures === 0) {
    return POLL_MS
  }
  const backoff = Math.min(POLL_MS * 2 ** failures, MAX_BACKOFF_MS)
  return backoff + Math.random() * POLL_MS
}

export function useScenarios() {
  const { client, keys } = useAuthedApi()
  return useQuery({
    queryKey: keys.scenarios(),
    queryFn: ({ signal }) => client.get<ScenarioPage>("/scenarios", { limit: 100 }, signal),
    select: (page) => [...page.items].sort((left, right) => left.id.localeCompare(right.id)),
  })
}

export function useDemoRun(runId: string) {
  const { client, keys } = useAuthedApi()
  return useQuery({
    queryKey: keys.demoRun(runId),
    queryFn: ({ signal }) => client.get<DemoRun>(`/demo-runs/${encodeURIComponent(runId)}`, undefined, signal),
    refetchInterval: (query) => nextPollDelay(query.state.data?.status, query.state.fetchFailureCount),
    refetchIntervalInBackground: false,
    retry: false,
  })
}

export function useEvidence(runId: string, enabled: boolean) {
  const { client, keys } = useAuthedApi()
  return useQuery({
    queryKey: keys.evidence(runId),
    enabled,
    queryFn: ({ signal }) => client.get<Evidence>(`/demo-runs/${encodeURIComponent(runId)}/evidence`, undefined, signal),
  })
}

export function useStartRun() {
  const { client } = useAuthedApi()
  return useMutation({
    // Sin reintento: si no hay respuesta, no se sabe si el run empezó.
    retry: false,
    mutationFn: (body: { scenario_id: string; seed: number }) =>
      client.post<DemoRunAccepted>("/demo-runs", { ...body, mode: "paired" }),
  })
}
