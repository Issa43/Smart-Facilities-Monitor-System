const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()

export const API_BASE_URL = (configuredBaseUrl || 'http://localhost:8000/api/v1').replace(
  /\/+$/,
  '',
)

const TOKEN_STORAGE_KEY = 'sflms.auth.tokens.v1'

export interface AuthTokens {
  access: string
  refresh: string
}

export interface PaginatedResponse<T> {
  count: number
  total_pages: number
  current_page: number
  page_size: number
  next: string | null
  previous: string | null
  results: T[]
}

interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
  auth?: boolean
  body?: BodyInit | Record<string, unknown> | null
  retryAfterRefresh?: boolean
}

let tokens: AuthTokens | null = readStoredTokens()
let refreshPromise: Promise<boolean> | null = null
const unauthorizedListeners = new Set<() => void>()

function readStoredTokens(): AuthTokens | null {
  if (typeof sessionStorage === 'undefined') return null
  try {
    const raw = sessionStorage.getItem(TOKEN_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<AuthTokens>
    return parsed.access && parsed.refresh
      ? { access: parsed.access, refresh: parsed.refresh }
      : null
  } catch {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY)
    return null
  }
}

function persistTokens(next: AuthTokens | null): void {
  tokens = next
  if (typeof sessionStorage === 'undefined') return
  if (next) sessionStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(next))
  else sessionStorage.removeItem(TOKEN_STORAGE_KEY)
}

export function setAuthTokens(next: AuthTokens): void {
  persistTokens(next)
}

export function clearAuthTokens(): void {
  persistTokens(null)
}

export function getRefreshToken(): string | null {
  return tokens?.refresh ?? null
}

export function getAccessToken(): string | null {
  return tokens?.access ?? null
}

export function hasStoredSession(): boolean {
  return tokens !== null
}

export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener)
  return () => {
    unauthorizedListeners.delete(listener)
  }
}

function notifyUnauthorized(): void {
  clearAuthTokens()
  unauthorizedListeners.forEach((listener) => listener())
}

function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE_URL}/${path.replace(/^\/+/, '')}`
}

export class ApiError extends Error {
  status: number
  details: unknown

  constructor(message: string, status = 400, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

function firstMessage(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value
  if (Array.isArray(value)) {
    for (const entry of value) {
      const message = firstMessage(entry)
      if (message) return message
    }
  }
  if (value && typeof value === 'object') {
    for (const entry of Object.values(value)) {
      const message = firstMessage(entry)
      if (message) return message
    }
  }
  return null
}

function messages(value: unknown): string[] {
  if (typeof value === 'string' && value.trim()) return [value]
  if (Array.isArray(value)) return value.flatMap(messages)
  if (value && typeof value === 'object') return Object.values(value).flatMap(messages)
  return []
}

function firstFieldMessage(value: unknown): string | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return firstMessage(value)
  }
  for (const [field, fieldErrors] of Object.entries(value)) {
    const fieldMessages = messages(fieldErrors)
    if (!fieldMessages.length) continue
    const message = fieldMessages.join(' ')
    if (field === 'detail' || field === 'non_field_errors') return message
    return `${field}: ${message}`
  }
  return null
}

async function responseBody(response: Response): Promise<unknown> {
  if (response.status === 204 || response.status === 205) return null
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

function errorFromResponse(response: Response, body: unknown): ApiError {
  const envelope =
    body && typeof body === 'object' && 'error' in body
      ? (body as { error?: { message?: unknown; details?: unknown } }).error
      : undefined
  const message =
    firstFieldMessage(envelope?.details) ??
    firstMessage(envelope?.message) ??
    firstMessage(body) ??
    `تعذّر إكمال الطلب (${response.status})`
  return new ApiError(message, response.status, envelope?.details ?? body)
}

async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    const refresh = tokens?.refresh
    if (!refresh) return false
    try {
      const response = await fetch(apiUrl('/auth/refresh/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ refresh }),
      })
      if (!response.ok) return false
      const body = (await response.json()) as { access?: string; refresh?: string }
      if (!body.access) return false
      setAuthTokens({ access: body.access, refresh: body.refresh ?? refresh })
      return true
    } catch {
      return false
    }
  })()
  try {
    return await refreshPromise
  } finally {
    refreshPromise = null
  }
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const {
    auth = true,
    body = null,
    retryAfterRefresh = true,
    headers: suppliedHeaders,
    ...requestInit
  } = options
  const headers = new Headers(suppliedHeaders)
  headers.set('Accept', 'application/json')
  if (auth && tokens?.access) headers.set('Authorization', `Bearer ${tokens.access}`)

  let requestBody: BodyInit | null = body as BodyInit | null
  if (body && !(body instanceof FormData) && !(body instanceof Blob) && typeof body !== 'string') {
    headers.set('Content-Type', 'application/json')
    requestBody = JSON.stringify(body)
  }

  let response: Response
  try {
    response = await fetch(apiUrl(path), { ...requestInit, headers, body: requestBody })
  } catch (error) {
    throw new ApiError(error instanceof Error ? error.message : 'تعذّر الاتصال بالخادم', 0, error)
  }
  if (response.status === 401 && auth && retryAfterRefresh) {
    if (await refreshAccessToken()) {
      return apiRequest<T>(path, { ...options, retryAfterRefresh: false })
    }
    notifyUnauthorized()
  }

  const parsed = await responseBody(response)
  if (!response.ok) throw errorFromResponse(response, parsed)
  return parsed as T
}

export interface DownloadedFile {
  blob: Blob
  filename: string
}

function responseFilename(response: Response, fallback: string): string {
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (utf8) return decodeURIComponent(utf8)
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? fallback
}

export async function downloadProtectedFile(
  path: string,
  fallbackFilename = 'download',
  retryAfterRefresh = true,
): Promise<DownloadedFile> {
  const headers = new Headers({ Accept: '*/*' })
  if (tokens?.access) headers.set('Authorization', `Bearer ${tokens.access}`)
  let response: Response
  try {
    response = await fetch(apiUrl(path), { headers })
  } catch (error) {
    throw new ApiError(error instanceof Error ? error.message : 'تعذّر الاتصال بالخادم', 0, error)
  }
  if (response.status === 401 && retryAfterRefresh) {
    if (await refreshAccessToken()) {
      return downloadProtectedFile(path, fallbackFilename, false)
    }
    notifyUnauthorized()
  }
  if (!response.ok) {
    const parsed = await responseBody(response)
    throw errorFromResponse(response, parsed)
  }
  return {
    blob: await response.blob(),
    filename: responseFilename(response, fallbackFilename),
  }
}

export function saveDownloadedFile(file: DownloadedFile): void {
  const url = URL.createObjectURL(file.blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = file.filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function fetchAllPages<T>(path: string): Promise<T[]> {
  const records: T[] = []
  let next: string | null = path
  let pageCount = 0
  while (next) {
    if (pageCount++ > 1000) throw new ApiError('تجاوزت الاستجابة الحد الآمن لعدد الصفحات', 500)
    const page: PaginatedResponse<T> = await apiRequest<PaginatedResponse<T>>(next)
    records.push(...page.results)
    next = page.next
  }
  return records
}

export function unsupported(message: string): never {
  throw new ApiError(message, 501)
}

export function notFound(what: string): never {
  throw new ApiError(`${what} غير موجود`, 404)
}
export function badRequest(message: string): never {
  throw new ApiError(message, 400)
}
