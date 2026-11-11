import { useQuery } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, ExternalLink } from "lucide-react"
import { Link } from "react-router"
import { StatTile } from "@/components/StatTile"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  api,
  formatAgo,
  formatBytes,
  formatDuration,
  formatUntil,
  formatWhen,
  type ManagedDownload,
  type ManagedDownloadsView,
} from "@/lib/api"

export function DownloadsPage() {
  const q = useQuery({ queryKey: ["downloads"], queryFn: () => api.get<ManagedDownloadsView>("downloads"), refetchInterval: 10_000 })
  const t = q.data?.totals
  return (
    <div className="grid max-w-5xl gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Downloads managed by RuTrackarr</CardTitle>
          <CardDescription>
            Releases grabbed through RuTrackarr that Sonarr/Radarr haven't imported yet, and every{" "}
            <Link to="/tracked" className="underline">
              tracked topic
            </Link>
            's torrent. An imported release whose topic isn't tracked is Sonarr's/Radarr's again (their post-import category) and
            drops off this list.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm">
          {q.isPending && <p className="text-muted-foreground">loading…</p>}
          {q.error && <p className="text-destructive">Could not load: {q.error.message}</p>}
          {q.data && !q.data.configured && <p className="text-muted-foreground">The download client proxy is off (no qBittorrent URL in settings).</p>}
          {q.data?.error && <p className="text-destructive">qBittorrent: {q.data.error}</p>}
          {t && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              <StatTile label="Torrents" value={t.torrents} />
              <StatTile label="Downloading" value={t.downloading} />
              <StatTile label="Tracked" value={t.tracked} />
              <StatTile label="Download speed" value={`${formatBytes(t.dlspeed)}/s`} />
              <StatTile label="Upload speed" value={`${formatBytes(t.upspeed)}/s`} />
              <StatTile label="Size" value={formatBytes(t.size)} />
            </div>
          )}
          {q.data?.configured && q.data.items.length === 0 && <p className="text-muted-foreground">Nothing in progress and nothing tracked.</p>}
          {q.data && q.data.items.length > 0 && (
            <ul className="grid gap-3">
              {q.data.items.map((d) => (
                <Row key={d.hash} d={d} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Row({ d }: { d: ManagedDownload }) {
  const done = d.status === "seeding"
  const pct = Math.round((d.progress ?? 0) * 1000) / 10
  const variant = d.status === "error" ? "destructive" : d.status === "downloading" ? "default" : "outline"
  const tr = d.tracked
  return (
    <li className="grid min-w-0 gap-1 border-b pb-3 last:border-b-0 last:pb-0">
      <div className="flex min-w-0 items-center gap-2">
        <Badge variant={variant}>{d.status}</Badge>
        {tr && (
          <Badge variant="outline" title={tr.source === "manual" ? "Tracked by hand" : "Tracked because Sonarr/Radarr grabbed it"}>
            {tr.source === "manual" ? "tracked by hand" : "tracked"}
          </Badge>
        )}
        {tr?.state === "paused" && (
          <Badge variant="secondary" title="Not monitored in Sonarr/Radarr: no update checks">
            paused
          </Badge>
        )}
        <span className="min-w-0 flex-1 truncate font-medium" title={d.title}>
          {d.title}
        </span>
        {d.topic_url && (
          <a href={d.topic_url} target="_blank" rel="noreferrer" className="inline-flex shrink-0 text-muted-foreground hover:text-foreground" aria-label="RuTracker topic">
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
        <span>{d.category || "no category"}</span>
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
        {tr && <span title={formatWhen(tr.last_update)}>topic updated {formatAgo(tr.last_update)}</span>}
        {tr && (
          <span title={tr.expires_at ? `Untracked ${formatWhen(tr.expires_at)} unless the topic updates` : "No TTL"}>
            {tr.expires_at ? `untracked ${formatUntil(tr.expires_at)} without an update (TTL ${tr.ttl} d)` : "no TTL"}
          </span>
        )}
      </div>
      {d.releases.length > 0 && (
        <ul className="grid gap-0.5 text-xs text-muted-foreground">
          {d.releases.map((r) => (
            <li key={r.release} className="flex min-w-0 gap-2">
              <span className="shrink-0">{r.app}</span>
              <span className="min-w-0 flex-1 truncate" title={r.release}>
                {r.release}
              </span>
              <span className="shrink-0">
                {r.in_queue === true ? "in queue" : r.in_queue === false ? `imported${r.category ? ` · ${r.category}` : ""}` : "queue unknown"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}
