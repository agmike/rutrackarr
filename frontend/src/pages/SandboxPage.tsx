import { useMutation } from "@tanstack/react-query"
import { CheckCircle2, ExternalLink, Pin, XCircle } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"
import { LibraryPicker } from "@/components/LibraryPicker"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, errorMessage, formatBytes, type LibraryItem, type SandboxResult } from "@/lib/api"

type Form = {
  kind: "tvsearch" | "movie" | "search"
  q: string
  tvdbid: string
  tmdbid: string
  imdbid: string
  season: string
  ep: string
}

const EMPTY: Form = { kind: "tvsearch", q: "", tvdbid: "", tmdbid: "", imdbid: "", season: "", ep: "" }
const num = (v: string) => (v.trim() && /^\d+$/.test(v.trim()) ? Number(v.trim()) : null)

function payload(f: Form, overrides: boolean, fresh: boolean) {
  return {
    kind: f.kind,
    q: f.q,
    tvdbid: f.kind === "tvsearch" ? num(f.tvdbid) : null,
    tmdbid: f.kind === "movie" ? num(f.tmdbid) : null,
    imdbid: f.kind === "movie" ? f.imdbid || null : null,
    season: f.kind === "movie" ? null : num(f.season),
    ep: f.kind === "movie" ? null : num(f.ep),
    overrides,
    fresh,
  }
}

function pinLink(f: Form, topicId: number, season: number | null) {
  const id = f.kind === "movie" ? f.tmdbid : f.tvdbid
  if (!id) return null
  const p = new URLSearchParams({ kind: f.kind === "movie" ? "movie" : "tv", id, pin: String(topicId) })
  if (season != null) p.set("season", String(season))
  return `/overrides?${p}`
}

export function SandboxPage() {
  const [form, setForm] = useState<Form>(EMPTY)
  const [picked, setPicked] = useState<LibraryItem | null>(null)
  const [fresh, setFresh] = useState(false)
  const [compare, setCompare] = useState(false)
  const [results, setResults] = useState<{ with: SandboxResult; without?: SandboxResult } | null>(null)
  const run = useMutation({
    mutationFn: async () => {
      const withO = await api.post<SandboxResult>("sandbox/search", payload(form, true, fresh))
      const without = compare ? await api.post<SandboxResult>("sandbox/search", payload(form, false, false)) : undefined
      return { with: withO, without }
    },
    onSuccess: setResults,
  })
  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value })
  const pick = (i: LibraryItem) => {
    setPicked(i)
    setForm({
      ...EMPTY,
      kind: i.kind,
      tvdbid: i.tvdbid ? String(i.tvdbid) : "",
      tmdbid: i.tmdbid ? String(i.tmdbid) : "",
      imdbid: i.imdbid ?? "",
      season: i.kind === "tvsearch" && i.seasons.length ? String(i.seasons[i.seasons.length - 1]) : "",
    })
  }
  return (
    <div className="grid max-w-5xl gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Simulate a Sonarr/Radarr search</CardTitle>
          <CardDescription>
            Runs the same search Sonarr or Radarr would send — titles from the metadata, overrides, every RuTracker query — and
            shows each topic found with its release name or why it was dropped. Not logged as a query. For a plain RuTracker
            search use the <Link to="/search" className="underline">Search</Link> page.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm">
          <LibraryPicker onPick={pick} />
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="grid gap-1">
              <Label>Search type</Label>
              <select className="h-9 rounded-md border bg-transparent px-2" value={form.kind} onChange={set("kind")}>
                <option value="tvsearch">TV (Sonarr)</option>
                <option value="movie">Film (Radarr)</option>
                <option value="search">Text (anime / RSS)</option>
              </select>
            </div>
            {form.kind === "tvsearch" && (
              <div className="grid gap-1">
                <Label>TVDB id</Label>
                <Input value={form.tvdbid} onChange={set("tvdbid")} inputMode="numeric" />
              </div>
            )}
            {form.kind === "movie" && (
              <>
                <div className="grid gap-1">
                  <Label>TMDb id</Label>
                  <Input value={form.tmdbid} onChange={set("tmdbid")} inputMode="numeric" />
                </div>
                <div className="grid gap-1">
                  <Label>IMDb id</Label>
                  <Input value={form.imdbid} onChange={set("imdbid")} placeholder="tt…" />
                </div>
              </>
            )}
            {form.kind !== "movie" && (
              <>
                <div className="grid gap-1">
                  <Label>Season</Label>
                  <Input value={form.season} onChange={set("season")} inputMode="numeric" />
                </div>
                <div className="grid gap-1">
                  <Label>Episode</Label>
                  <Input value={form.ep} onChange={set("ep")} inputMode="numeric" />
                </div>
              </>
            )}
          </div>
          {(form.kind === "search" || (!form.tvdbid && !form.tmdbid && !form.imdbid)) && (
            <div className="grid gap-1">
              <Label>Query</Label>
              <Input value={form.q} onChange={set("q")} placeholder="Title as Sonarr/Radarr would send it, e.g. “Sousou no Frieren 05”" />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-4">
            <Button onClick={() => run.mutate()} disabled={run.isPending}>
              {run.isPending ? "Searching…" : "Run"}
            </Button>
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} />
              Also without overrides
            </label>
            <label className="flex items-center gap-1.5" title="Ask RuTracker again instead of using cached results (uses the request budget)">
              <input type="checkbox" checked={fresh} onChange={(e) => setFresh(e.target.checked)} />
              Bypass cache
            </label>
            {picked && <span className="text-xs text-muted-foreground">{picked.title}</span>}
          </div>
          {run.error && <p className="text-destructive">{errorMessage(run.error)}</p>}
        </CardContent>
      </Card>
      {results && (
        <div className={results.without ? "grid gap-4 lg:grid-cols-2" : "grid gap-4"}>
          <ResultCard title={results.without ? "With overrides" : "Result"} r={results.with} form={form} />
          {results.without && <ResultCard title="Without overrides" r={results.without} form={form} />}
        </div>
      )}
    </div>
  )
}

function ResultCard({ title, r, form }: { title: string; r: SandboxResult; form: Form }) {
  const ctx = r.context
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>
          {r.kept} release{r.kept === 1 ? "" : "s"} for Sonarr/Radarr out of {r.rows.length} topics · {(r.took_ms / 1000).toFixed(1)} s
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {r.error && <p className="text-destructive">{r.error}</p>}
        {ctx?.error && <p className="text-muted-foreground">{ctx.error}</p>}
        {ctx?.title && (
          <div className="grid gap-1 text-xs text-muted-foreground">
            <span>
              Named as <span className="text-foreground">{ctx.title}</span>
              {ctx.year ? ` (${ctx.year})` : ""}
              {ctx.original_language ? ` · original language ${ctx.original_language}` : ""}
              {ctx.override ? " · override applied" : ""}
            </span>
            {ctx.seasons && ctx.seasons.length > 0 && (
              <span>Anime entries: {ctx.seasons.map((s) => `S${s.season ?? "?"}${s.offset ? ` +${s.offset}` : ""} ${s.names.filter(Boolean)[0] ?? ""}`).join(" · ")}</span>
            )}
          </div>
        )}
        {r.searches.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {r.searches.map((s, i) => (
              <Badge key={i} variant="outline" title={s.cached ? "from cache" : "asked RuTracker"}>
                {s.query} · {s.results}
                {s.cached ? " · cache" : ""}
              </Badge>
            ))}
          </div>
        )}
        <ul className="grid gap-2">
          {r.rows.map((row) => {
            const pin = !row.kept ? pinLink(form, row.topic_id, num(form.season)) : null
            return (
              <li key={row.topic_id} className="grid min-w-0 gap-0.5 border-b pb-2 last:border-b-0">
                <div className="flex min-w-0 items-start gap-2">
                  {row.kept ? (
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <XCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className={row.kept ? "min-w-0 flex-1 font-medium break-words" : "min-w-0 flex-1 break-words text-muted-foreground"}>
                    {row.kept ? row.release : row.title}
                  </span>
                  {row.tracked && <Badge variant="outline">tracked</Badge>}
                  {pin && (
                    <Link to={pin} className="shrink-0 text-muted-foreground hover:text-foreground" title="Pin this topic to the series (override)">
                      <Pin className="size-3.5" />
                    </Link>
                  )}
                  <a href={row.topic_url} target="_blank" rel="noreferrer" className="shrink-0 text-muted-foreground hover:text-foreground" aria-label="RuTracker topic">
                    <ExternalLink className="size-3.5" />
                  </a>
                </div>
                <div className="pl-6 text-xs text-muted-foreground break-words">
                  {row.kept ? row.title : <span className="text-amber-600 dark:text-amber-400">{row.reason}</span>}
                </div>
                <div className="pl-6 text-xs text-muted-foreground">
                  {row.forum} · {formatBytes(row.size)} · {row.seeders} seeders{row.language ? ` · ${row.language}` : ""}
                </div>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
