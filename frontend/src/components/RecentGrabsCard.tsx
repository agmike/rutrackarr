import { useQuery } from "@tanstack/react-query"
import { ExternalLink } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, formatAgo, formatWhen, type GrabsView, STATUS_ROWS } from "@/lib/api"

export function RecentGrabsCard() {
  const q = useQuery({
    queryKey: ["status-grabs"],
    queryFn: () => api.get<GrabsView>(`status/grabs?limit=${STATUS_ROWS}`),
    refetchInterval: 30_000,
  })
  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle>Recent grabs</CardTitle>
        <CardDescription>The last torrents Sonarr and Radarr fetched from RuTrackarr</CardDescription>
      </CardHeader>
      <CardContent className="text-sm">
        {q.isPending && <p className="text-muted-foreground">loading…</p>}
        {q.error && <p className="text-destructive">Could not load: {q.error.message}</p>}
        {q.data && q.data.items.length === 0 && <p className="text-muted-foreground">Nothing grabbed yet.</p>}
        <ul className="grid min-w-0 gap-1.5">
          {q.data?.items.map((g) => (
            <li key={g.hash} className="flex min-w-0 items-center gap-2">
              <span className="w-20 shrink-0 text-xs text-muted-foreground" title={formatWhen(g.served_at)}>
                {formatAgo(g.served_at)}
              </span>
              <span className="min-w-0 flex-1 truncate" title={g.release}>
                {g.release}
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">{g.via_proxy ? (g.category ?? "added") : "not added"}</span>
              {g.topic_url && (
                <a href={g.topic_url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground" aria-label="RuTracker topic">
                  <ExternalLink className="size-3.5" />
                </a>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
