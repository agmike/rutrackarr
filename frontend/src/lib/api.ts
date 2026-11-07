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

export type SystemStatus = { app: string; version: string; commit: string | null; repository: string }

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
  section: { kind: string; origin: string; video: boolean }
  language: Language
  parsed: ParsedTitle
}

export type Language = {
  tier: number // 1 original+subs, 2 RU voice, 3 EN dub, 4 other, 9 unknown
  label: string
  rank: number
  original: string | null
  en_subs: boolean
  notes: string[]
}

export type Audio = {
  lang: string | null
  voice: string | null
  original: boolean
  count: number
  info: string | null
  external: boolean | null
  partial: boolean
}

export type ParsedTitle = {
  raw: string
  names: string[]
  director: string | null
  prefix: string[]
  kinds: string[]
  season: number | null
  season_last: number | null
  episodes: {
    first: number | null
    last: number | null
    total: number | null
    specials: number | null
    specials_total: number | null
  } | null
  year: number | null
  year_end: number | null
  source: string | null
  uhd: boolean
  codec: string | null
  resolution: string | null
  hdr: string[]
  hardsub: string | null
  localized_video: boolean
  tags: string[]
  audio: Audio[]
  subs: string[]
  subs_unknown: boolean
  leftovers: string[]
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

export type ConnectionState = "ok" | "warn" | "error" | "off"
export type Connection = {
  id: string
  name: string
  state: ConnectionState
  detail: string
  version: string | null
  checks: { label: string; ok: boolean }[]
}
export type ConnectionsView = { checked_at: string; items: Connection[] }

export type DownloadStatus = "downloading" | "stalled" | "queued" | "stopped" | "error" | "seeding" | "unknown"
export type DownloadItem = {
  hash: string
  real_hash: string
  release: string
  category: string
  topic_id: number
  topic_url: string | null
  added_at: string | null
  status: DownloadStatus
  state: string | null
  progress: number | null
  size: number | null
  dlspeed: number | null
  upspeed: number | null
  eta: number | null
  ratio: number | null
  uploaded: number | null
  downloaded: number | null
  num_seeds: number | null
  num_leechs: number | null
  tracked?: boolean // a topic tracked by hand that no Sonarr/Radarr release uses yet
}
export type DownloadTotals = {
  releases: number
  torrents: number
  downloading: number
  seeding: number
  dlspeed: number
  upspeed: number
  uploaded: number
  size: number
}
export type DownloadsView = { configured: boolean; error?: string | null; items: DownloadItem[]; totals: DownloadTotals | null }

export type QueryStats = {
  hours: number
  queries: number
  cached: number
  errors: number
  rutracker_requests: number
  avg_ms: number | null
  max_ms: number | null
  by_caller: Record<string, number>
  by_kind: Record<string, number>
}
export type ServiceView = {
  version: string
  commit: string | null
  repository: string
  started_at: string
  uptime_seconds: number
  rutracker: { per_minute: number; last_minute: number; waiting: number; wait_seconds: number }
  queries_24h: QueryStats
  queries_7d: QueryStats
}
export type Grab = {
  hash: string
  release: string
  topic_id: number
  topic_url: string | null
  served_at: string | null
  via_proxy: boolean
  category: string | null
}
export type GrabsView = { items: Grab[] }
export type ActivityEvent = { at: string; kind: string; level: "info" | "warn" | "error"; message: string; topic_url: string | null }
export type EventsView = { items: ActivityEvent[] }
export type QueryEntry = {
  id: number
  at: string
  caller: string
  kind: string
  query: string
  results: number
  rutracker_requests: number
  duration_ms: number
  error: string | null
}
export type QueriesView = { items: QueryEntry[] }

export function formatBytes(n: number | null | undefined): string {
  if (n == null) return "—"
  const units = ["B", "KB", "MB", "GB", "TB"]
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0 || seconds >= 8640000) return "∞"
  if (seconds < 60) return `${Math.round(seconds)} s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ${Math.round((seconds % 3600) / 60)} min`
  return `${Math.floor(seconds / 86400)} d ${Math.round((seconds % 86400) / 3600)} h`
}

export function formatAgo(iso: string | null): string {
  if (!iso) return "—"
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return "just now"
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

export const del = <T,>(path: string) =>
  fetch(`api/${path}`, { method: "DELETE", headers: { Accept: "application/json" } }).then(async (res) => {
    const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null
    if (!res.ok) throw new ApiError(res.status, data?.detail ?? data)
    return data as T
  })

export type AlertItem = { key: string; level: "warn" | "error"; message: string; since: string }
export type AlertsView = { items: AlertItem[] }

export type Pin = { topic_id: number; season: number | null }
export type Override = {
  id?: number | null
  kind: "tv" | "movie"
  external_id: number
  title: string
  extra_titles: string[]
  replace_titles: boolean
  release_title: string | null
  season_offset: number | null
  include_regex: string | null
  exclude_regex: string | null
  pins: Pin[]
  note: string
  updated_at?: string | null
}
export type OverridesView = { items: Override[] }

export type LibraryItem = {
  kind: "tvsearch" | "movie"
  title: string
  year: number | null
  tvdbid: number | null
  tmdbid: number | null
  imdbid: string | null
  series_type: string | null
  seasons: number[]
}

export type SandboxRow = {
  topic_id: number
  title: string
  forum: string
  forum_id?: number | null
  size: number
  seeders: number
  release: string | null
  reason: string | null
  topic_url: string
  kept: boolean
  season: number | null
  categories: number[]
  language: string | null
  tracked?: boolean
}
export type SandboxResult = {
  took_ms: number
  error: string | null
  context: {
    kind?: string
    title?: string
    queries?: string[]
    year?: number | null
    original_language?: string | null
    seasons?: { season: number | null; offset: number; names: string[] }[]
    override?: Override | null
    error?: string
  } | null
  searches: { query: string; results: number; cached: boolean }[]
  kept: number
  rows: SandboxRow[]
}

export type QueryDetail = { topic_id: number; title: string; forum: string; release: string | null; reason: string | null; topic_url: string }
export type DroppedTopic = {
  topic_id: number
  title: string
  forum: string
  reason: string
  times: number
  last_seen: string
  last_query: string
  topic_url: string
}

export type TrackedTopic = {
  topic_id: number
  topic_url: string
  title: string
  forum: string
  source: "manual" | "grab"
  state: "active" | "gone"
  content_kind: "tv" | "movie" | null
  content_id: number | null
  season: number | null
  content_title: string | null
  created_at: string
  last_checked_at: string | null
  last_changed_at: string | null
  error: string | null
  releases: string[]
  in_queue: number
  torrent: {
    state: string
    progress: number
    size: number
    category: string
    dlspeed: number
    upspeed: number
    uploaded: number
    ratio: number
  } | null
}
export type TrackedView = { error: string | null; items: TrackedTopic[] }

export type TrackingView = {
  manual: number
  grabbed: number
  gone: number
  linked: number
  updated_7d: number
  failed_7d: number
  errors: { topic_id: number; title: string; error: string }[]
  due: number
  last_change: string | null
  feeds_at: string | null
  feeds: { forum_id: number; forum: string; tracked: number; status?: number; entries?: number; error?: string }[]
  auto_track: boolean
}
