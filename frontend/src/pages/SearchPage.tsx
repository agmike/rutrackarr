import { useQuery } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, Copy, Download, ExternalLink, Search } from "lucide-react"
import { Fragment, useMemo, useState } from "react"
import { useSearchParams } from "react-router"
import { SimulateSearch } from "@/pages/SandboxPage"
import { toast } from "sonner"
import { TrackButton } from "@/components/TrackButton"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, errorMessage, formatSize, type Language, type ParsedTitle, type SearchView } from "@/lib/api"
import { cn } from "@/lib/utils"

/** Results as JSON for building parser test data (no account details are part of results). */
function exportJson(view: SearchView): string {
  return JSON.stringify(
    {
      query: view.query,
      exported_at: new Date().toISOString(),
      results: view.results.map(({ topic_id, title, forum_id, forum, size, seeders, leechers, downloads, added }) => ({
        topic_id,
        title,
        forum_id,
        forum,
        size,
        seeders,
        leechers,
        downloads,
        added,
      })),
    },
    null,
    2,
  )
}

const TIER_STYLE: Record<number, string> = {
  1: "border-emerald-500/40 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  2: "border-sky-500/40 bg-sky-500/15 text-sky-700 dark:text-sky-300",
  3: "border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300",
  4: "text-muted-foreground",
  9: "text-muted-foreground border-dashed",
}

const VOICE: Record<string, string> = { dub: "Dub", mvo: "MVO", dvo: "DVO", avo: "AVO", vo: "VO" }

/** "S2 · ep 1–10 of 10 +11 sp · TV+Special · BDRip · 1080p · HDR10" */
function releaseParts(p: ParsedTitle): string[] {
  const out: string[] = []
  if (p.season != null) out.push(`S${p.season}${p.season_last ? `–${p.season_last}` : ""}`)
  const e = p.episodes
  if (e) {
    const range = e.first === e.last ? `ep ${e.first}` : `ep ${e.first}–${e.last}`
    const sp = e.specials ? ` +${e.specials} sp` : ""
    out.push(`${range} of ${e.total ?? "?"}${sp}`)
  }
  if (p.kinds.length) out.push(p.kinds.join("+"))
  if (p.source) out.push(`${p.uhd ? "UHD " : ""}${p.source}`)
  if (p.resolution) out.push(p.resolution)
  out.push(...p.hdr)
  if (p.hardsub) out.push(p.hardsub === "semi" ? "semi-hardsub" : p.hardsub === "russian" ? "RU hardsub" : "hardsub")
  return out
}

/** "Dub, MVO ×5, Original eng · Sub rus, eng" */
function audioLine(p: ParsedTitle): string {
  const audio = p.audio.map((a) => {
    const name = a.original ? "Original" : a.voice ? VOICE[a.voice] : "Audio"
    const lang = a.lang && !(a.lang === "rus" && a.voice) ? ` ${a.lang}` : ""
    const count = a.count > 1 ? ` ×${a.count}` : ""
    const ext = a.external ? " (ext)" : ""
    const part = a.partial ? " (part)" : ""
    return `${name}${lang}${count}${ext}${part}`
  })
  const subs = p.subs.length ? `Sub ${p.subs.join(", ")}` : p.subs_unknown ? "Sub ?" : ""
  return [audio.join(", "), subs].filter(Boolean).join(" · ")
}

function LanguageBadge({ language }: { language: Language }) {
  return (
    <Badge
      variant="outline"
      className={cn("whitespace-nowrap", TIER_STYLE[language.tier])}
      title={language.notes.join("; ")}
    >
      {language.label}
    </Badge>
  )
}

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const mode = params.get("mode") === "arr" ? "arr" : "rutracker"
  const pick = (m: "rutracker" | "arr") => setParams(m === "arr" ? { mode: "arr" } : {}, { replace: true })
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={mode === "rutracker" ? "default" : "outline"} onClick={() => pick("rutracker")}>
          RuTracker
        </Button>
        <Button size="sm" variant={mode === "arr" ? "default" : "outline"} onClick={() => pick("arr")}>
          As Sonarr/Radarr
        </Button>
        <span className="text-xs text-muted-foreground">
          {mode === "arr"
            ? "The search Sonarr/Radarr would send — titles, overrides, tracked topics — and why each topic is kept or dropped"
            : "A plain RuTracker search, every result parsed and ranked"}
        </span>
      </div>
      {mode === "arr" ? <SimulateSearch /> : <RuTrackerSearch />}
    </div>
  )
}

function RuTrackerSearch() {
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""
  const [draft, setDraft] = useState(q)
  const [showAll, setShowAll] = useState(false)
  const [byLanguage, setByLanguage] = useState(true)
  const [open, setOpen] = useState<Set<number>>(new Set())
  const { data, error, isFetching } = useQuery({
    queryKey: ["search", q],
    queryFn: () => api.get<SearchView>(`rutracker/search?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length > 0,
    staleTime: 5 * 60_000,
  })
  const rows = useMemo(() => {
    if (!data) return []
    const visible = data.results.filter((r) => showAll || r.section.video)
    if (!byLanguage) return visible
    return [...visible].sort((a, b) => a.language.rank - b.language.rank || b.seeders - a.seeders)
  }, [data, showAll, byLanguage])
  const hidden = data ? data.results.filter((r) => !r.section.video).length : 0
  const toggle = (id: number) =>
    setOpen((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <div className="grid gap-4">
      <form
        className="flex max-w-2xl gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setParams(draft.trim() ? { q: draft.trim() } : {})
        }}
      >
        <Input placeholder="Search RuTracker, e.g. Хёка" value={draft} onChange={(e) => setDraft(e.target.value)} />
        <Button type="submit" disabled={isFetching}>
          <Search /> {isFetching ? "Searching…" : "Search"}
        </Button>
      </form>
      <p className="text-muted-foreground text-sm">
        RuTracker results (first page, up to 50) with what RuTrackarr reads from each title. Language preference:
        original + subtitles, then Russian voice (dub › multi-voice › two-voice › author's › single-voice), then
        English dub.
      </p>
      {error && <p className="text-destructive text-sm">{errorMessage(error)}</p>}
      {data && (
        <Card>
          <CardContent className="p-0">
            <div className="text-muted-foreground flex flex-wrap items-center gap-2 px-4 pt-3 text-sm">
              <span className="mr-auto">
                {rows.length} results in {(data.took_ms / 1000).toFixed(1)} s
                {hidden > 0 && !showAll && ` · ${hidden} from non-video sections hidden`}
              </span>
              <Button variant="ghost" size="sm" onClick={() => setByLanguage((v) => !v)}>
                {byLanguage ? "Sorted by language" : "RuTracker order"}
              </Button>
              {hidden > 0 && (
                <Button variant="ghost" size="sm" onClick={() => setShowAll((v) => !v)}>
                  {showAll ? "Hide non-video" : "Show all sections"}
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  await navigator.clipboard.writeText(exportJson(data))
                  toast.success(`Copied ${data.results.length} results as JSON`)
                }}
              >
                <Copy /> Copy JSON
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  const blob = new Blob([exportJson(data)], { type: "application/json" })
                  const a = document.createElement("a")
                  a.href = URL.createObjectURL(blob)
                  a.download = `rutracker-${data.query.replace(/[^\p{L}\p{N}]+/gu, "-").slice(0, 40) || "search"}.json`
                  a.click()
                  URL.revokeObjectURL(a.href)
                }}
              >
                <Download /> Download
              </Button>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-6" />
                  <TableHead>Title</TableHead>
                  <TableHead>Language</TableHead>
                  <TableHead>Forum</TableHead>
                  <TableHead className="text-right">Size</TableHead>
                  <TableHead className="text-right">S / L</TableHead>
                  <TableHead className="text-right">Added</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => {
                  const expanded = open.has(r.topic_id)
                  return (
                    <Fragment key={r.topic_id}>
                      <TableRow className={cn(!r.section.video && "opacity-60")}>
                        <TableCell className="align-top">
                          <button
                            type="button"
                            className="text-muted-foreground hover:text-foreground"
                            aria-label={expanded ? "Hide parsed fields" : "Show parsed fields"}
                            onClick={() => toggle(r.topic_id)}
                          >
                            {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                          </button>
                        </TableCell>
                        <TableCell className="max-w-xl whitespace-normal">
                          <a href={r.url} target="_blank" rel="noreferrer" className="hover:underline">
                            {r.title}
                            <ExternalLink className="ml-1 inline size-3 opacity-60" />
                          </a>
                          {r.approved && (
                            <Badge variant="outline" className="ml-2">
                              {r.approved}
                            </Badge>
                          )}
                          {r.section.video && (
                            <div className="text-muted-foreground mt-1 flex flex-wrap gap-x-2 text-xs">
                              {releaseParts(r.parsed).map((part) => (
                                <span key={part}>{part}</span>
                              ))}
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="align-top whitespace-normal">
                          {r.section.video ? (
                            <div className="grid gap-1">
                              <LanguageBadge language={r.language} />
                              <span className="text-muted-foreground max-w-56 text-xs">{audioLine(r.parsed)}</span>
                            </div>
                          ) : (
                            <span className="text-muted-foreground text-xs">not video</span>
                          )}
                        </TableCell>
                        <TableCell className="text-muted-foreground max-w-48 align-top whitespace-normal text-xs">
                          {r.forum}
                        </TableCell>
                        <TableCell className="text-right align-top whitespace-nowrap">{formatSize(r.size)}</TableCell>
                        <TableCell className="text-right align-top whitespace-nowrap">
                          <span className="text-emerald-500">{r.seeders}</span> / {r.leechers}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-right align-top whitespace-nowrap">
                          {r.added ? new Date(r.added).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell className="align-top">{r.section.video && <TrackButton topic={r} />}</TableCell>
                      </TableRow>
                      {expanded && (
                        <TableRow>
                          <TableCell />
                          <TableCell colSpan={7}>
                            <pre className="bg-muted max-h-96 overflow-auto rounded p-3 text-xs whitespace-pre-wrap">
                              {JSON.stringify(
                                { section: r.section, language: r.language, ...r.parsed, raw: undefined },
                                null,
                                2,
                              )}
                            </pre>
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
