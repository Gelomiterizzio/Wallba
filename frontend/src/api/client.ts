/** Cliente HTTP: cookies de sesión, CSRF en mutaciones y error común. No decide permisos. */

export type ApiErrorDetail = { field: string; code: string }

export class ApiRequestError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly details: ApiErrorDetail[]

  constructor(status: number, code: string, message: string, requestId: string | null, details: ApiErrorDetail[]) {
    super(message)
    this.name = "ApiRequestError"
    this.status = status
    this.code = code
    this.requestId = requestId
    this.details = details
  }
}

export type QueryParams = Record<string, string | number | boolean | null | undefined>

export type DownloadResult = { blob: Blob; headers: Headers }

export type ApiClient = {
  get<T>(path: string, params?: QueryParams, signal?: AbortSignal): Promise<T>
  post<T>(path: string, body?: unknown): Promise<T>
  download(path: string, params?: QueryParams): Promise<DownloadResult>
}

type ClientOptions = {
  baseUrl?: string
  getCsrfToken: () => string | null
  onUnauthorized: () => void
}

const NETWORK_MESSAGE = "No se pudo contactar con el servidor."

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object"
}

export function readApiError(status: number, payload: unknown): ApiRequestError {
  const error = isRecord(payload) && isRecord(payload.error) ? payload.error : {}
  const details = Array.isArray(error.details)
    ? error.details.flatMap((item: unknown) =>
        isRecord(item) && typeof item.field === "string" && typeof item.code === "string"
          ? [{ field: item.field, code: item.code }]
          : [],
      )
    : []
  // Un cuerpo inesperado nunca se muestra: podría contener detalles internos.
  return new ApiRequestError(
    status,
    typeof error.code === "string" ? error.code : "UNEXPECTED_RESPONSE",
    typeof error.message === "string" ? error.message : "La operación no se completó.",
    typeof error.request_id === "string" ? error.request_id : null,
    details,
  )
}

export function buildUrl(baseUrl: string, path: string, params: QueryParams = {}): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value))
    }
  }
  const suffix = query.toString()
  return `${baseUrl}${path}${suffix ? `?${suffix}` : ""}`
}

export function createApiClient({ baseUrl = "/api/v1", getCsrfToken, onUnauthorized }: ClientOptions): ApiClient {
  async function send(url: string, init: RequestInit): Promise<Response> {
    let response: Response
    try {
      response = await fetch(url, { ...init, credentials: "include" })
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") {
        throw reason
      }
      throw new ApiRequestError(0, "NETWORK_ERROR", NETWORK_MESSAGE, null, [])
    }
    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => null)
      if (response.status === 401) {
        onUnauthorized()
      }
      throw readApiError(response.status, payload)
    }
    return response
  }

  async function parse<T>(response: Response): Promise<T> {
    if (response.status === 204) {
      return undefined as T
    }
    try {
      return (await response.json()) as T
    } catch {
      throw new ApiRequestError(response.status, "CONTRACT_ERROR", "El servidor devolvió una respuesta inesperada.", null, [])
    }
  }

  return {
    async get<T>(path: string, params?: QueryParams, signal?: AbortSignal) {
      const response = await send(buildUrl(baseUrl, path, params), {
        method: "GET",
        signal,
        headers: { accept: "application/json" },
      })
      return parse<T>(response)
    },
    async post<T>(path: string, body?: unknown) {
      const headers: Record<string, string> = { accept: "application/json" }
      const csrf = getCsrfToken()
      if (csrf) {
        headers["x-csrf-token"] = csrf
      }
      if (body !== undefined) {
        headers["content-type"] = "application/json"
      }
      const response = await send(buildUrl(baseUrl, path), {
        method: "POST",
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      return parse<T>(response)
    },
    async download(path: string, params?: QueryParams) {
      const response = await send(buildUrl(baseUrl, path, params), { method: "GET" })
      return { blob: await response.blob(), headers: response.headers }
    },
  }
}
