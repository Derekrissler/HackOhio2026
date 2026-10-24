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

/** Retry server/network errors, never 4xx: a 403 won't fix itself. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false
  return failureCount < 2
}
