import { useQuery } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { StatTile } from "@/components/StatTile"
import { api, formatBytes, formatDuration, type DownloadItem, type DownloadsView } from "@/lib/api"

function app(category: string): string {
  const c = category.toLowerCase()
  if (c.startsWith("sonarr") || c.startsWith("tv")) return "Sonarr"
  if (c.startsWith("radarr") || c.startsWith("movie")) return "Radarr"
  return category || "—"
}

function Row({ d }: { d: DownloadItem }) {
  const done = d.status === "seeding"
  const pct = Math.round((d.progress ?? 0) * 1000) / 10
  const variant = d.status === "error" ? "destructive" : d.status === "downloading" ? "default" : "outline"
  return (
    <li className="grid gap-1 border-b pb-2 last:border-b-0 last:pb-0">
      <div className="flex min-w-0 items-center gap-2">
        <Badge variant={variant}>{d.status}</Badge>
        <span className="min-w-0 flex-1 truncate font-medium" title={d.release}>
          {d.release}
        </span>
        {d.topic_url && (
          <a href={d.topic_url} target="_blank" rel="noreferrer" className="shrink-0 text-muted-foreground hover:text-foreground" aria-label="RuTracker topic">
            <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>
      {!done && (
        <div className="h-1.5 overflow-hidden rounded bg-muted">
          <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground tabular-nums">
        <span>{app(d.category)}</span>
        <span>{done ? formatBytes(d.size) : `${pct}% of ${formatBytes(d.size)}`}</span>
        {!done && (
          <span className="inline-flex items-center gap-0.5">
            <ArrowDown className="size-3" />
            {formatBytes(d.dlspeed)}/s
          </span>
        )}
        <span className="inline-flex items-center gap-0.5">
          <ArrowUp className="size-3" />
          {formatBytes(d.upspeed)}/s
        </span>
        {!done && d.status === "downloading" && <span>{formatDuration(d.eta)} left</span>}
        <span title="Uploaded / ratio">
          up {formatBytes(d.uploaded)} · ratio {(d.ratio ?? 0).toFixed(2)}
        </span>
        {d.num_leechs != null && d.num_seeds != null && (
          <span title="Connected seeds / leechers">
            {d.num_seeds} seeds · {d.num_leechs} peers
          </span>
        )}
      </div>
    </li>
  )
}

export function DownloadsCard() {
  const q = useQuery({ queryKey: ["status-downloads"], queryFn: () => api.get<DownloadsView>("status/downloads"), refetchInterval: 10_000 })
  const t = q.data?.totals
  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle>Downloads</CardTitle>
        <CardDescription>Releases grabbed through RuTrackarr's download client, live from qBittorrent</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        {q.isPending && <p className="text-muted-foreground">loading…</p>}
        {q.error && <p className="text-destructive">Could not load: {q.error.message}</p>}
        {q.data && !q.data.configured && <p className="text-muted-foreground">The download client proxy is off (no qBittorrent URL in settings).</p>}
        {q.data?.error && <p className="text-destructive">qBittorrent: {q.data.error}</p>}
        {t && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <StatTile label="Downloading" value={t.downloading} />
            <StatTile label="Seeding" value={t.seeding} hint={`${t.releases} releases in ${t.torrents} topic torrents`} />
            <StatTile label="Download speed" value={`${formatBytes(t.dlspeed)}/s`} />
            <StatTile label="Upload speed" value={`${formatBytes(t.upspeed)}/s`} />
            <StatTile label="Uploaded" value={formatBytes(t.uploaded)} hint="All tracked topic torrents, since added" />
            <StatTile label="Size" value={formatBytes(t.size)} />
          </div>
        )}
        {q.data?.configured && q.data.items.length === 0 && <p className="text-muted-foreground">No releases tracked.</p>}
        {q.data && q.data.items.length > 0 && (
          <ul className="grid gap-2">
            {q.data.items.map((d) => (
              <Row key={d.hash} d={d} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
