import createClient from 'openapi-fetch'
import type { paths } from './schema'
import { getAccessToken, refreshAccessToken } from '../auth/tokenStore'

export const apiClient = createClient<paths>({ baseUrl: '/api' })

// Body eines Requests zwischenspeichern, falls nach einem 401 (abgelaufenes
// Access-Token) mit neuem Token wiederholt werden muss – der Body-Stream
// eines Request-Objekts lässt sich nur einmal lesen.
const pendingBodies = new Map<string, string>()

apiClient.use({
  async onRequest({ request, id }) {
    const token = getAccessToken()
    if (token) {
      request.headers.set('Authorization', `Bearer ${token}`)
    }
    pendingBodies.set(id, await request.clone().text())
    return request
  },
  async onResponse({ request, response, id }) {
    const bodyText = pendingBodies.get(id)
    pendingBodies.delete(id)

    if (response.status !== 401) {
      return response
    }

    const newToken = await refreshAccessToken()
    if (!newToken) {
      return response
    }

    const retryHeaders = new Headers(request.headers)
    retryHeaders.set('Authorization', `Bearer ${newToken}`)
    return fetch(request.url, {
      method: request.method,
      headers: retryHeaders,
      body: bodyText || undefined,
    })
  },
})

export class ApiError extends Error {
  status: number
  code: string | undefined

  constructor(status: number, code: string | undefined, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

interface ApiResult<T> {
  data?: T
  error?: unknown
  response: Response
}

/** Wirft ApiError statt {data, error} zurückzugeben – praktischer in
 * queryFn/mutationFn von TanStack Query, das auf Exceptions statt
 * Rückgabewerten basiert. */
export function unwrap<T>(result: ApiResult<T>): T {
  if (result.error !== undefined) {
    const detail = result.error as { detail?: string; code?: string }
    throw new ApiError(result.response.status, detail.code, detail.detail ?? 'Unbekannter Fehler.')
  }
  if (result.data === undefined) {
    throw new ApiError(result.response.status, undefined, 'Leere Antwort vom Server.')
  }
  return result.data
}
