export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

/** GET /api{path}. `userId` is sent as X-Demo-User, the backend's only identity input. */
export async function apiGet<T>(path: string, userId?: number): Promise<T> {
  const headers: HeadersInit = userId === undefined ? {} : { 'X-Demo-User': String(userId) }
  const res = await fetch(`/api${path}`, { headers })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail ?? res.statusText)
  }
  return res.json() as Promise<T>
}

/** Real analytics identity is a Supabase JWT, independent of X-Demo-User. */
export async function analyticsGet<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`/api/analytics${path}`, {
    headers: { Authorization: `Bearer ${token}` }, signal, cache: 'no-store',
  })
  if (!res.ok) throw new ApiError(res.status, 'Analytics request failed')
  return res.json() as Promise<T>
}

/** Retry server/network errors, never 4xx: a 403 won't fix itself. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false
  return failureCount < 2
}
