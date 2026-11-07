import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, ExternalLink, Info, XCircle } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, formatAgo, formatWhen, type EventsView } from "@/lib/api"

const ICON = {
  info: <Info className="size-3.5 text-muted-foreground" />,
  warn: <AlertTriangle className="size-3.5 text-amber-600 dark:text-amber-400" />,
  error: <XCircle className="size-3.5 text-destructive" />,
}

export function ActivityCard() {
  const q = useQuery({ queryKey: ["status-events"], queryFn: () => api.get<EventsView>("status/events?limit=25"), refetchInterval: 15_000 })
  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle>Activity</CardTitle>
        <CardDescription>Grabs, torrents added, moved and removed, RuTracker outages</CardDescription>
      </CardHeader>
      <CardContent className="text-sm">
        {q.isPending && <p className="text-muted-foreground">loading…</p>}
        {q.error && <p className="text-destructive">Could not load: {q.error.message}</p>}
        {q.data && q.data.items.length === 0 && <p className="text-muted-foreground">Nothing yet.</p>}
        <ul className="grid gap-1.5">
          {q.data?.items.map((e, i) => (
            <li key={`${e.at}-${i}`} className="flex min-w-0 items-start gap-2">
              <span className="w-16 shrink-0 pt-0.5 text-xs text-muted-foreground" title={formatWhen(e.at)}>
                {formatAgo(e.at)}
              </span>
              <span className="shrink-0 pt-0.5">{ICON[e.level] ?? ICON.info}</span>
              <span className="min-w-0 flex-1 break-words">{e.message}</span>
              {e.topic_url && (
                <a href={e.topic_url} target="_blank" rel="noreferrer" className="shrink-0 pt-0.5 text-muted-foreground hover:text-foreground" aria-label="RuTracker topic">
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
