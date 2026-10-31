import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useState, type ReactNode } from "react"
import { ApiRequestError } from "../api/client"
import { SessionProvider } from "./session"

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        // Solo fallos transitorios de lectura. Los 4xx no cambian al reintentar.
        retry: (count, error) =>
          error instanceof ApiRequestError && (error.status === 0 || error.status >= 500) && count < 2,
      },
      // Una mutación repetida a ciegas podría iniciar otra ejecución.
      mutations: { retry: false },
    },
  })
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(createQueryClient)
  return (
    <QueryClientProvider client={client}>
      <SessionProvider>{children}</SessionProvider>
    </QueryClientProvider>
  )
}
