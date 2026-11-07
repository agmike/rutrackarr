import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { StatTile } from "@/components/StatTile"
import { api, formatDuration, formatWhen, type ServiceView } from "@/lib/api"

export function ServiceCard() {
  const q = useQuery({ queryKey: ["status-service"], queryFn: () => api.get<ServiceView>("status/service"), refetchInterval: 10_000 })
  const s = q.data
  const day = s?.queries_24h
  const cacheRate = day && day.queries ? Math.round((day.cached / day.queries) * 100) : null
  const rt = s?.rutracker
  return (
    <Card>
      <CardHeader>
        <CardTitle>Service</CardTitle>
        <CardDescription>RuTrackarr backend</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          {q.isPending && <span className="text-muted-foreground">checking…</span>}
          {q.error && <Badge variant="destructive">unreachable</Badge>}
          {s && (
            <>
              <Badge>online</Badge>
              <span className="text-muted-foreground">version {s.version}</span>
              <span className="text-muted-foreground" title={`since ${formatWhen(s.started_at)}`}>
                · up {formatDuration(s.uptime_seconds)}
              </span>
            </>
          )}
        </div>
        {s && day && rt && (
          <div className="grid grid-cols-2 gap-2">
            <StatTile label="Queries, 24 h" value={day.queries} hint={`${s.queries_7d.queries} in 7 days`} />
            <StatTile label="From cache" value={cacheRate == null ? "—" : `${cacheRate}%`} hint="Answered without asking RuTracker" />
            <StatTile label="Avg. answer" value={day.avg_ms == null ? "—" : `${(day.avg_ms / 1000).toFixed(1)} s`} hint={day.max_ms ? `slowest ${(day.max_ms / 1000).toFixed(1)} s` : undefined} />
            <StatTile
              label="RuTracker, last minute"
              value={`${rt.last_minute}/${rt.per_minute}`}
              hint={rt.waiting ? `${rt.waiting} waiting, ~${rt.wait_seconds} s` : "Requests in the last minute / limit"}
            />
          </div>
        )}
        {rt && rt.waiting > 0 && (
          <span className="text-xs text-muted-foreground">
            {rt.waiting} RuTracker request{rt.waiting === 1 ? "" : "s"} waiting their turn — about {formatDuration(rt.wait_seconds)}
          </span>
        )}
        {day && day.errors > 0 && <span className="text-xs text-destructive">{day.errors} failed queries in 24 h</span>}
      </CardContent>
    </Card>
  )
}
