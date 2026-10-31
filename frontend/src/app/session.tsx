/** Estado de sesión. Los roles orientan la interfaz; el servidor autoriza cada petición. */
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react"
import { ApiRequestError, createApiClient, type ApiClient } from "../api/client"
import { queryKeys, sessionKey } from "../api/queryKeys"
import type { Session } from "../api/types"

export type SessionStatus = "loading" | "anonymous" | "authenticated" | "unavailable"

type SessionContextValue = {
  status: SessionStatus
  session: Session | null
  error: ApiRequestError | null
  client: ApiClient
  retry: () => void
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const SessionContext = createContext<SessionContextValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const csrfRef = useRef<string | null>(null)

  const client = useMemo(
    () =>
      createApiClient({
        getCsrfToken: () => csrfRef.current,
        onUnauthorized: () => {
          // Sesión vencida: ningún dato del usuario anterior queda en memoria.
          csrfRef.current = null
          const identity = queryClient.getQueryData<Session | null>(sessionKey)?.principal_id
          if (identity) {
            queryClient.removeQueries({ predicate: (query) => query.queryKey[1] === identity })
          }
          queryClient.setQueryData(sessionKey, null)
        },
      }),
    [queryClient],
  )

  const query = useQuery<Session | null, ApiRequestError>({
    queryKey: sessionKey,
    retry: false,
    staleTime: Infinity,
    queryFn: async ({ signal }) => {
      try {
        return await client.get<Session>("/auth/me", undefined, signal)
      } catch (reason) {
        if (reason instanceof ApiRequestError && reason.status === 401) {
          return null
        }
        throw reason
      }
    },
  })

  const session = query.data ?? null

  useEffect(() => {
    csrfRef.current = session?.csrf_token ?? null
  }, [session])

  const retry = useCallback(() => {
    void query.refetch()
  }, [query])

  // Conserva solo la entrada de sesión: borrarla también dejaría al observador sin avisar.
  const setIdentity = useCallback(
    (next: Session | null) => {
      csrfRef.current = next?.csrf_token ?? null
      queryClient.setQueryData(sessionKey, next)
      queryClient.removeQueries({ predicate: (query) => query.queryKey[1] !== sessionKey[1] })
    },
    [queryClient],
  )

  const login = useCallback(
    async (username: string, password: string) => {
      // El login solo devuelve csrf_token y roles; la identidad completa sale de /auth/me.
      await client.post("/auth/login", { username, password })
      setIdentity(await client.get<Session>("/auth/me"))
    },
    [client, setIdentity],
  )

  const logout = useCallback(async () => {
    try {
      await client.post<void>("/auth/logout")
    } finally {
      // Aunque el servidor no responda, esta pestaña deja de mostrar datos sensibles.
      setIdentity(null)
    }
  }, [client, setIdentity])

  const status: SessionStatus = query.isPending
    ? "loading"
    : query.isError
      ? "unavailable"
      : session
        ? "authenticated"
        : "anonymous"

  const value = useMemo(
    () => ({ status, session, error: query.error, client, retry, login, logout }),
    [status, session, query.error, client, retry, login, logout],
  )
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext)
  if (!value) {
    throw new Error("useSession requiere SessionProvider")
  }
  return value
}

/** Para pantallas dentro del shell, donde la sesión ya está garantizada. */
export function useAuthedApi() {
  const { client, session } = useSession()
  if (!session) {
    throw new Error("useAuthedApi requiere una sesión")
  }
  return {
    client,
    session,
    keys: queryKeys(session.principal_id),
    can: (role: string) => session.roles.includes(role),
  }
}
