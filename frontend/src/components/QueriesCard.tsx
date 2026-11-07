import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, formatAgo, formatWhen, type QueriesView, type ServiceView } from "@/lib/api"

const KIND: Record<string, string> = { search: "text", tvsearch: "TV", movie: "movie", rss: "RSS" }

function counts(m: Record<string, number>, names: Record<string, string> = {}): string {
  const parts = Object.entries(m).sort((a, b) => b[1] - a[1])
  return parts.length ? parts.map(([k, v]) => `${names[k] ?? k} ${v}`).join(" · ") : "—"
}

export function QueriesCard() {
  const [errorsOnly, setErrorsOnly] = useState(false)
  const service = useQuery({ queryKey: ["status-service"], queryFn: () => api.get<ServiceView>("status/service"), refetchInterval: 10_000 })
  const q = useQuery({
    queryKey: ["status-queries", errorsOnly],
    queryFn: () => api.get<QueriesView>(`status/queries?limit=8${errorsOnly ? "&errors=true" : ""}`),
    refetchInterval: 15_000,
  })
  const day = service.data?.queries_24h
  const week = service.data?.queries_7d
  return (
    <Card className="md:col-span-2">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="grid gap-1.5">
          <CardTitle>Queries</CardTitle>
          <CardDescription>
            Searches from Sonarr and Radarr ·{" "}
            <Link to="/queries" className="underline">
              all queries, results and dropped topics
            </Link>
          </CardDescription>
        </div>
        <Button variant={errorsOnly ? "default" : "outline"} size="sm" onClick={() => setErrorsOnly((v) => !v)}>
          Errors only
        </Button>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {day && week && (
          <div className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
            <span>24 h by app: {counts(day.by_caller)}</span>
            <span>24 h by type: {counts(day.by_kind, KIND)}</span>
            <span>
              7 days: {week.queries} queries, {week.rutracker_requests} RuTracker requests, {week.errors} errors
            </span>
          </div>
        )}
        {q.data && q.data.items.length === 0 && <p className="text-muted-foreground">{errorsOnly ? "No failed queries." : "No queries yet."}</p>}
        <ul className="grid gap-1">
          {q.data?.items.map((e, i) => (
            <li key={`${e.at}-${i}`} className="grid gap-0.5">
              <div className="flex min-w-0 items-center gap-2">
                <span className="w-16 shrink-0 text-xs text-muted-foreground" title={formatWhen(e.at)}>
                  {formatAgo(e.at)}
                </span>
                <span className="w-14 shrink-0 text-xs text-muted-foreground">{e.caller}</span>
                <span className="w-10 shrink-0 text-xs text-muted-foreground">{KIND[e.kind] ?? e.kind}</span>
                <span className="min-w-0 flex-1 truncate" title={e.query}>
                  {e.query}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums" title={`${e.rutracker_requests} RuTracker requests`}>
                  {e.error ? "failed" : `${e.results} found`} · {(e.duration_ms / 1000).toFixed(1)} s{e.rutracker_requests === 0 && !e.error ? " · cache" : ""}
                </span>
              </div>
              {e.error && <span className="pl-[8.5rem] text-xs text-destructive">{e.error}</span>}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
