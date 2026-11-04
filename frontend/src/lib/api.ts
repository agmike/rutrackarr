// API calls are relative: the document's <base href> carries the URL base
// (e.g. /rutrackarr/), so "api/..." resolves to /rutrackarr/api/... at runtime.
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`api/${path}`, { headers: { Accept: "application/json" } })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

export type SystemStatus = { app: string; version: string }
