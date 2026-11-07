import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, Pencil, Plus, Trash2, Upload } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useSearchParams } from "react-router"
import { toast } from "sonner"
import { LibraryPicker } from "@/components/LibraryPicker"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api, del, errorMessage, formatAgo, type Override, type OverridesView } from "@/lib/api"

type Draft = {
  id?: number | null
  kind: "tv" | "movie"
  external_id: string
  title: string
  extra_titles: string
  replace_titles: boolean
  release_title: string
  season_offset: string
  include_regex: string
  exclude_regex: string
  pins: string
  note: string
}

const BLANK: Draft = {
  kind: "tv", external_id: "", title: "", extra_titles: "", replace_titles: false, release_title: "",
  season_offset: "", include_regex: "", exclude_regex: "", pins: "", note: "",
}

function toDraft(o: Override): Draft {
  return {
    id: o.id,
    kind: o.kind,
    external_id: String(o.external_id),
    title: o.title,
    extra_titles: o.extra_titles.join("\n"),
    replace_titles: o.replace_titles,
    release_title: o.release_title ?? "",
    season_offset: o.season_offset == null ? "" : String(o.season_offset),
    include_regex: o.include_regex ?? "",
    exclude_regex: o.exclude_regex ?? "",
    pins: o.pins.map((p) => (p.season == null ? `${p.topic_id}` : `${p.topic_id} S${p.season}`)).join("\n"),
    note: o.note,
  }
}

function fromDraft(d: Draft) {
  return {
    kind: d.kind,
    external_id: Number(d.external_id),
    title: d.title,
    extra_titles: d.extra_titles.split("\n").map((t) => t.trim()).filter(Boolean),
    replace_titles: d.replace_titles,
    release_title: d.release_title || null,
    season_offset: d.season_offset.trim() ? Number(d.season_offset) : null,
    include_regex: d.include_regex || null,
    exclude_regex: d.exclude_regex || null,
    pins: d.pins
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        const m = /(\d+)(?:\D+(\d+))?/.exec(l.replace(/^https?:\/\/\S*?t=/, ""))
        return { topic_id: Number(m?.[1] ?? 0), season: m?.[2] ? Number(m[2]) : null }
      }),
    note: d.note,
  }
}

const textarea = "min-h-20 rounded-md border bg-transparent px-3 py-2 text-sm font-mono"

export function OverridesPage() {
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const list = useQuery({ queryKey: ["overrides"], queryFn: () => api.get<OverridesView>("overrides") })
  const [draft, setDraft] = useState<Draft | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // Links from the query log / sandbox: ?kind=tv&id=…&pin=…&season=… — open (or start) that
  // series' override with the topic pinned.
  useEffect(() => {
    const id = params.get("id")
    if (!id || !list.data) return
    const kind = params.get("kind") === "movie" ? "movie" : "tv"
    const existing = list.data.items.find((o) => o.kind === kind && String(o.external_id) === id)
    const d = existing ? toDraft(existing) : { ...BLANK, kind, external_id: id } as Draft
    const pin = params.get("pin")
    if (pin && !d.pins.split("\n").some((l) => l.trim().startsWith(pin))) {
      const season = params.get("season")
      d.pins = [d.pins, season ? `${pin} S${season}` : pin].filter(Boolean).join("\n")
    }
    setDraft(d)
    setParams({}, { replace: true })
  }, [params, list.data, setParams])

  const save = useMutation({
    mutationFn: (d: Draft) => api.post<Override>("overrides", fromDraft(d)),
    onSuccess: () => {
      toast.success("Override saved — applies to the next search")
      setDraft(null)
      qc.invalidateQueries({ queryKey: ["overrides"] })
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const remove = useMutation({
    mutationFn: (id: number) => del(`overrides/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["overrides"] }),
    onError: (e) => toast.error(errorMessage(e)),
  })
  const exportAll = async () => {
    const data = await api.get<unknown>("overrides/export")
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }))
    const a = Object.assign(document.createElement("a"), { href: url, download: "rutrackarr-overrides.json" })
    a.click()
    URL.revokeObjectURL(url)
  }
  const importFile = async (file: File) => {
    try {
      const r = await api.post<{ imported: number }>("overrides/import", JSON.parse(await file.text()))
      toast.success(`Imported ${r.imported} overrides`)
      qc.invalidateQueries({ queryKey: ["overrides"] })
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  return (
    <div className="grid max-w-4xl gap-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2">
          <div className="grid gap-1.5">
            <CardTitle>Overrides</CardTitle>
            <CardDescription>
              Per series or film: extra RuTracker search titles, the title releases are named after, a season offset, title
              filters, and topics pinned to the series. Used by ID searches from Sonarr (TVDB id) and Radarr (TMDb id).
            </CardDescription>
          </div>
          <div className="flex shrink-0 gap-1">
            <Button size="sm" onClick={() => setDraft({ ...BLANK })}>
              <Plus /> New
            </Button>
            <Button size="sm" variant="outline" onClick={exportAll} title="Export all as JSON">
              <Download />
            </Button>
            <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} title="Import JSON (replaces matching overrides)">
              <Upload />
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept="application/json"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])}
            />
          </div>
        </CardHeader>
        <CardContent className="text-sm">
          {list.data?.items.length === 0 && !draft && <p className="text-muted-foreground">No overrides yet.</p>}
          <ul className="grid gap-2">
            {list.data?.items.map((o) => (
              <li key={o.id} className="flex min-w-0 items-start gap-2 border-b pb-2 last:border-b-0">
                <div className="grid min-w-0 flex-1 gap-0.5">
                  <span className="font-medium">
                    {o.title || `${o.kind === "tv" ? "TVDB" : "TMDb"} ${o.external_id}`}{" "}
                    <span className="text-xs text-muted-foreground">
                      {o.kind === "tv" ? "TVDB" : "TMDb"} {o.external_id} · {formatAgo(o.updated_at ?? null)}
                    </span>
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {o.extra_titles.length > 0 && (
                      <Badge variant="outline">{o.replace_titles ? "only" : "+"} {o.extra_titles.length} titles</Badge>
                    )}
                    {o.release_title && <Badge variant="outline">named “{o.release_title}”</Badge>}
                    {o.season_offset != null && <Badge variant="outline">season {o.season_offset > 0 ? "+" : ""}{o.season_offset}</Badge>}
                    {o.include_regex && <Badge variant="outline">include /{o.include_regex}/</Badge>}
                    {o.exclude_regex && <Badge variant="outline">exclude /{o.exclude_regex}/</Badge>}
                    {o.pins.length > 0 && <Badge variant="outline">{o.pins.length} pinned topics</Badge>}
                  </div>
                  {o.note && <span className="text-xs text-muted-foreground">{o.note}</span>}
                </div>
                <Button size="sm" variant="ghost" onClick={() => setDraft(toDraft(o))} aria-label="Edit">
                  <Pencil />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label="Delete"
                  onClick={() => o.id && confirm(`Delete the override for ${o.title || o.external_id}?`) && remove.mutate(o.id)}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      {draft && <Editor draft={draft} setDraft={setDraft} onSave={() => save.mutate(draft)} saving={save.isPending} />}
    </div>
  )
}

function Editor({ draft, setDraft, onSave, saving }: { draft: Draft; setDraft: (d: Draft | null) => void; onSave: () => void; saving: boolean }) {
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setDraft({ ...draft, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value })
  return (
    <Card>
      <CardHeader>
        <CardTitle>{draft.id ? "Edit override" : "New override"}</CardTitle>
        <CardDescription>Applies from the next search; use the Sandbox to compare with and without it.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {!draft.id && (
          <LibraryPicker
            onPick={(i) =>
              setDraft({
                ...draft,
                kind: i.kind === "movie" ? "movie" : "tv",
                external_id: String(i.kind === "movie" ? i.tmdbid ?? "" : i.tvdbid ?? ""),
                title: i.title,
              })
            }
          />
        )}
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-1">
            <Label>Type</Label>
            <select className="h-9 rounded-md border bg-transparent px-2" value={draft.kind} onChange={set("kind")} disabled={!!draft.id}>
              <option value="tv">Series (TVDB id)</option>
              <option value="movie">Film (TMDb id)</option>
            </select>
          </div>
          <div className="grid gap-1">
            <Label>{draft.kind === "tv" ? "TVDB id" : "TMDb id"}</Label>
            <Input value={draft.external_id} onChange={set("external_id")} inputMode="numeric" disabled={!!draft.id} />
          </div>
          <div className="grid gap-1">
            <Label>Name (for this list)</Label>
            <Input value={draft.title} onChange={set("title")} />
          </div>
        </div>
        <div className="grid gap-1">
          <Label>Extra RuTracker search titles (one per line)</Label>
          <textarea className={textarea} value={draft.extra_titles} onChange={set("extra_titles")} placeholder="Детектив с Бейкер-стрит" />
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" checked={draft.replace_titles} onChange={set("replace_titles")} />
            Search only these titles (not the automatic Russian / original / English ones)
          </label>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1">
            <Label>Release title</Label>
            <Input value={draft.release_title} onChange={set("release_title")} placeholder="Name releases after this instead of Sonarr's title" />
          </div>
          <div className="grid gap-1">
            <Label>Season offset</Label>
            <Input value={draft.season_offset} onChange={set("season_offset")} placeholder="e.g. -1: a topic's “Сезон 2” is TVDB season 1" />
          </div>
          <div className="grid gap-1">
            <Label>Include only titles matching (regex)</Label>
            <Input value={draft.include_regex} onChange={set("include_regex")} className="font-mono" />
          </div>
          <div className="grid gap-1">
            <Label>Exclude titles matching (regex)</Label>
            <Input value={draft.exclude_regex} onChange={set("exclude_regex")} className="font-mono" placeholder="CAMRip|TS\b" />
          </div>
        </div>
        <div className="grid gap-1">
          <Label>Pinned topics (one per line: topic id or URL, optionally a season — “6918173 S2”)</Label>
          <textarea className={textarea} value={draft.pins} onChange={set("pins")} />
          <span className="text-xs text-muted-foreground">
            A pinned topic counts as this series (and season) whatever its title says, when a search for the series finds it.
            If searches don't find it, add one of its names as an extra title.
          </span>
        </div>
        <div className="grid gap-1">
          <Label>Note</Label>
          <Input value={draft.note} onChange={set("note")} />
        </div>
        <div className="flex gap-2">
          <Button onClick={onSave} disabled={saving || !draft.external_id}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button variant="outline" onClick={() => setDraft(null)}>
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
