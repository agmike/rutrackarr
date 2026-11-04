import { useQuery } from "@tanstack/react-query"
import { Copy, Download, ExternalLink, Search } from "lucide-react"
import { useState } from "react"
import { useSearchParams } from "react-router"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, errorMessage, formatSize, type SearchView } from "@/lib/api"

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

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""
  const [draft, setDraft] = useState(q)
  const { data, error, isFetching } = useQuery({
    queryKey: ["search", q],
    queryFn: () => api.get<SearchView>(`rutracker/search?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length > 0,
    staleTime: 5 * 60_000,
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
        Raw RuTracker results, titles exactly as the site shows them (first page, up to 50).
      </p>
      {error && <p className="text-destructive text-sm">{errorMessage(error)}</p>}
      {data && (
        <Card>
          <CardContent className="p-0">
            <div className="text-muted-foreground flex items-center gap-2 px-4 pt-3 text-sm">
              <span className="mr-auto">
                {data.results.length} results in {(data.took_ms / 1000).toFixed(1)} s
              </span>
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
                  <TableHead>Title</TableHead>
                  <TableHead>Forum</TableHead>
                  <TableHead className="text-right">Size</TableHead>
                  <TableHead className="text-right">S / L</TableHead>
                  <TableHead className="text-right">Added</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.results.map((r) => (
                  <TableRow key={r.topic_id}>
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
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-48 whitespace-normal text-xs">{r.forum}</TableCell>
                    <TableCell className="text-right whitespace-nowrap">{formatSize(r.size)}</TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <span className="text-emerald-500">{r.seeders}</span> / {r.leechers}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-right whitespace-nowrap">
                      {r.added ? new Date(r.added).toLocaleDateString() : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
