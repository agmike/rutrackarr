// API calls are relative: the document's <base href> carries the URL base
// (e.g. /rutrackarr/), so "api/..." resolves to /rutrackarr/api/... at runtime.

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(`HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`api/${path}`, {
    method,
    headers: { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data)
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
}

/** Field-level validation errors from a 422 response, if any. */
export function fieldErrors(err: unknown): Record<string, string> {
  if (err instanceof ApiError && err.status === 422) {
    const d = err.detail as { errors?: Record<string, string> } | null
    return d?.errors ?? {}
  }
  return {}
}

export type SystemStatus = { app: string; version: string }

export type SettingsView = {
  values: Record<string, string | number>
  secrets: Record<string, boolean>
  api_key_pinned: boolean
}

export type ApiKeyView = { api_key: string; pinned: boolean }

export type RuTrackerSession = {
  configured: boolean
  has_session: boolean
  username: string | null
  logged_in_at: string | null
  last_ok_at: string | null
  cf_solved_at: string | null
  last_error: string | null
  last_error_at: string | null
}

export type LoginResult = { status: "ok" | "captcha"; username: string | null; captcha_id: string | null }

export type SearchResult = {
  topic_id: number
  title: string
  forum_id: number | null
  forum: string
  size: number
  seeders: number
  leechers: number
  downloads: number
  added: string | null
  author: string
  approved: string | null
  url: string
}

export type SearchView = { query: string; took_ms: number; results: SearchResult[] }

/** Human-readable message from an API error. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.detail
    if (typeof d === "string") return d
    return `HTTP ${err.status}`
  }
  return err instanceof Error ? err.message : String(err)
}

export function formatSize(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"]
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(i >= 3 ? 1 : 0)} ${units[i]}`
}

export function formatWhen(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString()
}
