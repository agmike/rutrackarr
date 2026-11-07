import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, RefreshCw, Trash2, Unlink } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { api, del, errorMessage, formatAgo, formatBytes, type TrackedTopic, type TrackedView } from "@/lib/api"

export function TrackedPage() {
  const qc = useQueryClient()
  const [topic, setTopic] = useState("")
  const list = useQuery({ queryKey: ["tracked"], queryFn: () => api.get<TrackedView>("tracked"), refetchInterval: 15_000 })
  const refresh = () => qc.invalidateQueries({ queryKey: ["tracked"] })
  const track = useMutation({
    mutationFn: () => api.post<{ title: string }>("tracked", { topic }),
    onSuccess: (r) => {
      toast.success(`Tracking ${r.title}`)
      setTopic("")
      refresh()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const items = list.data?.items ?? []
  return (
    <div className="grid max-w-5xl gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Track a topic</CardTitle>
          <CardDescription>
            RuTrackarr downloads it now (into the tracking category, Sonarr/Radarr don't see it) and follows its updates —
            RuTracker's section feeds are read every few minutes, and a changed topic's new torrent replaces the old one in place
            (only new or changed files download). When
            a Sonarr/Radarr search matches it, it's offered like any result — a grab then uses the download that's already
            there. Results on the <Link to="/search" className="underline">Search</Link> page can be tracked too.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (topic.trim()) track.mutate()
            }}
          >
            <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="https://rutracker.org/forum/viewtopic.php?t=… or the topic number" />
            <Button type="submit" disabled={track.isPending || !topic.trim()}>
              {track.isPending ? "Adding…" : "Track"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Tracked topics</CardTitle>
          <CardDescription>
            {items.filter((t) => t.state === "active").length} tracked · by hand ones are RuTrackarr's (their torrent stays in
            the tracking category); grabbed ones are Sonarr's/Radarr's, followed for updates
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm">
          {list.data?.error && <p className="mb-2 text-destructive">qBittorrent: {list.data.error}</p>}
          {list.data && items.length === 0 && <p className="text-muted-foreground">Nothing tracked yet.</p>}
          <ul className="grid gap-3">
            {items.map((t) => (
              <Row key={t.topic_id} t={t} onChange={refresh} />
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

function Row({ t, onChange }: { t: TrackedTopic; onChange: () => void }) {
  const check = useMutation({
    mutationFn: () => api.post<{ result: string }>(`tracked/${t.topic_id}/check`),
    onSuccess: (r) => {
      if (r.result === "updated") toast.success("Updated to the topic's new torrent")
      else if (r.result === "unchanged") toast.info("No update")
      else toast.warning(r.result)
      onChange()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const untrack = useMutation({
    mutationFn: () => api.post(`tracked/${t.topic_id}/untrack`),
    onSuccess: onChange,
    onError: (e) => toast.error(errorMessage(e)),
  })
  const remove = useMutation({
    mutationFn: () => del<{ notes: string[] }>(`tracked/${t.topic_id}?delete_files=true`),
    onSuccess: (r) => {
      toast.success(r.notes.join("; ") || "Removed")
      onChange()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const q = t.torrent
  const pct = q ? Math.round(q.progress * 1000) / 10 : null
  const confirmRemove = () => {
    const parts = [`Remove “${t.title}”: stop tracking and delete its torrent with the downloaded files?`]
    if (t.in_queue)
      parts.push(
        `${t.in_queue} Sonarr/Radarr release(s) use it; ones still in their queue are removed there too (not blocklisted).`,
      )
    parts.push("Episodes already imported stay in the library (hardlinks).")
    if (confirm(parts.join("\n\n"))) remove.mutate()
  }
  return (
    <li className="grid min-w-0 gap-1 border-b pb-3 last:border-b-0">
      <div className="flex min-w-0 items-center gap-2">
        <Badge variant={t.state === "gone" ? "destructive" : t.source === "manual" ? "default" : "outline"}>
          {t.state === "gone" ? "gone" : t.source === "manual" ? "by hand" : "grabbed"}
        </Badge>
        <span className="min-w-0 flex-1 truncate font-medium" title={t.title}>
          {t.title}
        </span>
        <a href={t.topic_url} target="_blank" rel="noreferrer" className="shrink-0 text-muted-foreground hover:text-foreground" aria-label="RuTracker topic">
          <ExternalLink className="size-3.5" />
        </a>
        <Button size="sm" variant="ghost" title="Check for an update now" onClick={() => check.mutate()} disabled={check.isPending}>
          <RefreshCw className={check.isPending ? "animate-spin" : ""} />
        </Button>
        <Button size="sm" variant="ghost" title="Stop tracking (the torrent stays)" onClick={() => untrack.mutate()} disabled={untrack.isPending}>
          <Unlink />
        </Button>
        <Button size="sm" variant="ghost" title="Remove: stop tracking and delete the torrent" onClick={confirmRemove} disabled={remove.isPending}>
          <Trash2 />
        </Button>
      </div>
      {q && pct !== null && pct < 100 && (
        <div className="h-1.5 overflow-hidden rounded bg-muted">
          <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
        </div>
      )}
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
        <span>{t.forum}</span>
        {q && (
          <>
            <span>{pct === 100 ? formatBytes(q.size) : `${pct}% of ${formatBytes(q.size)}`}</span>
            <span>{q.category || "no category"}</span>
            <span>
              up {formatBytes(q.uploaded)} · ratio {q.ratio.toFixed(2)}
            </span>
          </>
        )}
        <span>tracked {formatAgo(t.created_at)}</span>
        <span>checked {t.last_checked_at ? formatAgo(t.last_checked_at) : "not yet"}</span>
        {t.last_changed_at && <span>updated {formatAgo(t.last_changed_at)}</span>}
      </div>
      <div className="text-xs text-muted-foreground">
        {t.content_id ? (
          <span>
            {t.content_kind === "tv" ? "Series" : "Film"} {t.content_kind === "tv" ? "TVDB" : "TMDb"} {t.content_id}
            {t.season != null ? ` · season ${t.season}` : ""}
            {t.content_title ? ` — ${t.content_title}` : ""}
          </span>
        ) : (
          <span>Not matched by a Sonarr/Radarr search yet</span>
        )}
        {t.releases.length > 0 && <span> · used by: {t.releases.join("; ")}</span>}
      </div>
      {t.error && <span className="text-xs text-destructive">{t.error}</span>}
    </li>
  )
}

