import { useQuery } from "@tanstack/react-query"
import { ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, formatBytes, formatDuration, type DownloadItem, type DownloadsView } from "@/lib/api"

const ACTIVE = new Set(["downloading", "stalled", "queued", "stopped", "error", "unknown"])

function StatusBadge({ d }: { d: DownloadItem }) {
  const variant = d.status === "error" || d.status === "missing" ? "destructive" : d.status === "downloading" ? "default" : "outline"
  return <Badge variant={variant}>{d.status}</Badge>
}

function app(category: string): string {
  const c = category.toLowerCase()
  return c.startsWith("sonarr") || c.startsWith("tv") ? "Sonarr" : c.startsWith("radarr") || c.startsWith("movie") ? "Radarr" : category
}

export function DownloadsCard() {
  const q = useQuery({
    queryKey: ["status-downloads"],
    queryFn: () => api.get<DownloadsView>("status/downloads"),
    refetchInterval: 10_000,
  })
  const items = q.data?.items ?? []
  const active = items.filter((d) => ACTIVE.has(d.status))
  const seeding = items.filter((d) => d.status === "seeding")
  const missing = items.filter((d) => d.status === "missing")
  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle>Downloads</CardTitle>
        <CardDescription>
          Releases grabbed through RuTrackarr's download client
          {q.data?.configured && items.length > 0 &&
            ` · ${active.length} in progress, ${seeding.length} seeding${missing.length ? `, ${missing.length} removed from qBittorrent` : ""}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {q.isPending && <p className="text-muted-foreground">loading…</p>}
        {q.error && <p className="text-destructive">Could not load: {q.error.message}</p>}
        {q.data && !q.data.configured && (
          <p className="text-muted-foreground">The download client proxy is off (no qBittorrent URL in settings).</p>
        )}
        {q.data?.error && <p className="text-destructive">qBittorrent: {q.data.error}</p>}
        {q.data?.configured && active.length === 0 && <p className="text-muted-foreground">Nothing downloading.</p>}
        {active.map((d) => (
          <div key={d.hash} className="grid gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge d={d} />
              <span className="text-xs text-muted-foreground">{app(d.category)}</span>
              <span className="min-w-0 flex-1 truncate font-medium" title={d.release}>
                {d.release}
              </span>
              {d.topic_url && (
                <a href={d.topic_url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground" aria-label="RuTracker topic">
                  <ExternalLink className="size-3.5" />
                </a>
              )}
            </div>
            <div className="h-1.5 overflow-hidden rounded bg-muted">
              <div className="h-full bg-primary transition-all" style={{ width: `${Math.round((d.progress ?? 0) * 100)}%` }} />
            </div>
            <div className="flex flex-wrap gap-x-4 text-xs text-muted-foreground">
              <span>{Math.round((d.progress ?? 0) * 1000) / 10}% of {formatBytes(d.size)}</span>
              {d.status === "downloading" && <span>{formatBytes(d.dlspeed)}/s</span>}
              {d.status === "downloading" && <span>{formatDuration(d.eta)} left</span>}
            </div>
          </div>
        ))}
        {missing.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Removed from qBittorrent: {missing.map((d) => d.release).join("; ")}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
