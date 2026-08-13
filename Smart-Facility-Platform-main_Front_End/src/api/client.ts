/**
 * The seam between the UI and its data source.
 *
 * Every function in the sibling api/*.ts modules is async and returns exactly
 * the shape a REST endpoint would. Today they read from a localStorage-backed
 * store; to move to a real backend, replace those function bodies with fetch()
 * calls and nothing above this layer changes — not the pages, not the query
 * keys, not the types.
 */

/** Simulated network latency. Real enough that loading skeletons actually show. */
export const API_LATENCY_MS = 260

export function delay(ms: number = API_LATENCY_MS): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status = 400) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Throws a 404 with an Arabic message. Returns `never` so callers narrow correctly. */
export function notFound(what: string): never {
  throw new ApiError(`${what} غير موجود`, 404)
}

/** Throws a 400 — used for the business rules the requirements define. */
export function badRequest(message: string): never {
  throw new ApiError(message, 400)
}

/** Stable-enough unique id for records created during a session. */
export function newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

/**
 * Sequential human-readable reference, e.g. nextReference('INC', 42) -> "INC-2026-0043".
 */
export function nextReference(prefix: string, existingCount: number): string {
  const year = new Date().getFullYear()
  return `${prefix}-${year}-${String(existingCount + 1).padStart(4, '0')}`
}

export function nowIso(): string {
  return new Date().toISOString()
}
