import { useQuery } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, ExternalLink, FlaskConical, Pin } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, formatAgo, formatWhen, type DroppedTopic, type QueriesView, type QueryDetail, type QueryEntry } from "@/lib/api"

const KIND: Record<string, string> = { search: "text", tvsearch: "TV", movie: "movie", rss: "RSS" }
type Tab = "recent" | "errors" | "empty" | "dropped"

/** "tvdb:410378 S1 E5" → what the sandbox and the override form need. */
function parseQuery(q: string) {
  const tvdb = /tvdb:(\d+)/.exec(q)?.[1]
  const tmdb = /tmdb:(\d+)/.exec(q)?.[1]
  const imdb = /\b(tt\d+)\b/.exec(q)?.[1]
  const season = /\bS(\d+)\b/.exec(q)?.[1]
  return { tvdb, tmdb, imdb, season }
}

function overrideLink(query: string, topicId?: number) {
  const p = parseQuery(query)
  const id = p.tvdb ?? p.tmdb
  if (!id) return null
  const params = new URLSearchParams({ kind: p.tvdb ? "tv" : "movie", id })
  if (topicId) params.set("pin", String(topicId))
  if (topicId && p.season) params.set("season", p.season)
  return `/overrides?${params}`
}

export function QueriesPage() {
  const [tab, setTab] = useState<Tab>("recent")
  const tabs: [Tab, string][] = [
    ["recent", "Recent"],
    ["errors", "Failed"],
    ["empty", "No results"],
    ["dropped", "Dropped topics"],
  ]
  return (
    <div className="grid max-w-5xl gap-4">
      <div className="flex flex-wrap gap-2">
        {tabs.map(([t, label]) => (
          <Button key={t} size="sm" variant={tab === t ? "default" : "outline"} onClick={() => setTab(t)}>
            {label}
          </Button>
        ))}
      </div>
      {tab === "dropped" ? <Dropped /> : <QueryList tab={tab} />}
    </div>
  )
}

function QueryList({ tab }: { tab: Exclude<Tab, "dropped"> }) {
  const [open, setOpen] = useState<number | null>(null)
  const filter = tab === "errors" ? "&errors=true" : tab === "empty" ? "&empty=true" : ""
  const q = useQuery({
    queryKey: ["queries-page", tab],
    queryFn: () => api.get<QueriesView>(`status/queries?limit=100${filter}`),
    refetchInterval: 15_000,
  })
  const descr = {
    recent: "Searches from Sonarr and Radarr, newest first. Open one to see every RuTracker topic it found and why it was kept or dropped.",
    errors: "Searches that failed (RuTracker or FlareSolverr trouble).",
    empty: "Searches that found nothing for Sonarr/Radarr — candidates for an override (extra titles, season offset).",
  }[tab]
  return (
    <Card>
      <CardHeader>
        <CardTitle>{{ recent: "Recent queries", errors: "Failed queries", empty: "Queries without results" }[tab]}</CardTitle>
        <CardDescription>{descr}</CardDescription>
      </CardHeader>
      <CardContent className="text-sm">
        {q.data?.items.length === 0 && <p className="text-muted-foreground">Nothing here.</p>}
        <ul className="grid gap-1">
          {q.data?.items.map((e) => (
            <QueryRow key={e.id} e={e} open={open === e.id} toggle={() => setOpen(open === e.id ? null : e.id)} />
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

function QueryRow({ e, open, toggle }: { e: QueryEntry; open: boolean; toggle: () => void }) {
  const ov = overrideLink(e.query)
  const p = parseQuery(e.query)
  const sandbox = p.tvdb || p.tmdb ? `/sandbox` : null
  return (
    <li className="grid min-w-0 gap-1 border-b pb-1 last:border-b-0">
      <button type="button" onClick={toggle} className="flex min-w-0 items-center gap-2 text-left hover:text-foreground">
        {open ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0" />}
        <span className="w-16 shrink-0 text-xs text-muted-foreground" title={formatWhen(e.at)}>
          {formatAgo(e.at)}
        </span>
        <span className="w-14 shrink-0 text-xs text-muted-foreground">{e.caller}</span>
        <span className="w-10 shrink-0 text-xs text-muted-foreground">{KIND[e.kind] ?? e.kind}</span>
        <span className="min-w-0 flex-1 truncate" title={e.query}>
          {e.query}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
          {e.error ? "failed" : `${e.results} found`} · {(e.duration_ms / 1000).toFixed(1)} s{e.rutracker_requests === 0 && !e.error ? " · cache" : ""}
        </span>
      </button>
      {e.error && <span className="pl-6 text-xs text-destructive">{e.error}</span>}
      {open && (
        <div className="grid gap-2 pl-6">
          <div className="flex flex-wrap gap-3 text-xs">
            {ov && (
              <Link to={ov} className="inline-flex items-center gap-1 underline">
                <Pin className="size-3" /> Override for this {p.tvdb ? "series" : "film"}
              </Link>
            )}
            {sandbox && (
              <Link to={sandbox} className="inline-flex items-center gap-1 underline">
                <FlaskConical className="size-3" /> Try in the sandbox
              </Link>
            )}
          </div>
          <Details id={e.id} query={e.query} />
        </div>
      )}
    </li>
  )
}

function Details({ id, query }: { id: number; query: string }) {
  const q = useQuery({ queryKey: ["query-detail", id], queryFn: () => api.get<{ items: QueryDetail[] }>(`status/queries/${id}`) })
  if (q.isPending) return <p className="text-xs text-muted-foreground">loading…</p>
  if (!q.data?.items.length) return <p className="text-xs text-muted-foreground">No topics recorded for this query (none found, or too old).</p>
  return (
    <ul className="grid gap-1 text-xs">
      {q.data.items.map((d) => {
        const pin = !d.release ? overrideLink(query, d.topic_id) : null
        return (
          <li key={d.topic_id} className="grid min-w-0 gap-0.5">
            <div className="flex min-w-0 items-start gap-2">
              <span className={d.release ? "min-w-0 flex-1 break-words" : "min-w-0 flex-1 break-words text-muted-foreground"}>
                {d.release ?? d.title}
              </span>
              {pin && (
                <Link to={pin} title="Pin this topic to the series" className="shrink-0 text-muted-foreground hover:text-foreground">
                  <Pin className="size-3.5" />
                </Link>
              )}
              <a href={d.topic_url} target="_blank" rel="noreferrer" className="shrink-0 text-muted-foreground hover:text-foreground">
                <ExternalLink className="size-3.5" />
              </a>
            </div>
            {!d.release && <span className="text-amber-600 dark:text-amber-400">{d.reason}</span>}
          </li>
        )
      })}
    </ul>
  )
}

function Dropped() {
  const [reason, setReason] = useState("")
  const q = useQuery({
    queryKey: ["dropped", reason],
    queryFn: () => api.get<{ items: DroppedTopic[] }>(`status/dropped?limit=200&reason=${encodeURIComponent(reason)}`),
  })
  const filters: [string, string][] = [
    ["", "All"],
    ["not ", "Not the series/film"],
    ["unparsed", "Unparsed titles"],
    ["season", "Other season"],
    ["episode", "Other episodes"],
  ]
  return (
    <Card>
      <CardHeader>
        <CardTitle>Dropped topics</CardTitle>
        <CardDescription>
          Topics RuTracker returned that weren't offered to Sonarr/Radarr, with the reason. A topic that does belong to the
          series can be pinned to it.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <div className="flex flex-wrap gap-2">
          {filters.map(([r, label]) => (
            <Button key={label} size="sm" variant={reason === r ? "default" : "outline"} onClick={() => setReason(r)}>
              {label}
            </Button>
          ))}
        </div>
        {q.data?.items.length === 0 && <p className="text-muted-foreground">Nothing here.</p>}
        <ul className="grid gap-2">
          {q.data?.items.map((d) => {
            const pin = overrideLink(d.last_query, d.topic_id)
            return (
              <li key={`${d.topic_id}-${d.reason}`} className="grid min-w-0 gap-0.5 border-b pb-2 last:border-b-0">
                <div className="flex min-w-0 items-start gap-2">
                  <span className="min-w-0 flex-1 break-words">{d.title}</span>
                  {pin && (
                    <Link to={pin} title="Pin this topic to the series" className="shrink-0 text-muted-foreground hover:text-foreground">
                      <Pin className="size-3.5" />
                    </Link>
                  )}
                  <a href={d.topic_url} target="_blank" rel="noreferrer" className="shrink-0 text-muted-foreground hover:text-foreground">
                    <ExternalLink className="size-3.5" />
                  </a>
                </div>
                <span className="text-xs text-amber-600 dark:text-amber-400">{d.reason}</span>
                <span className="text-xs text-muted-foreground">
                  {d.forum} · seen {d.times}× · last {formatAgo(d.last_seen)} for “{d.last_query}”
                </span>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
