import { useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, CircleDashed, RefreshCw, XCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, formatAgo, type ConnectionState, type ConnectionsView } from "@/lib/api"

const ICON: Record<ConnectionState, React.ReactNode> = {
  ok: <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400" aria-label="ok" />,
  warn: <AlertTriangle className="size-4 text-amber-600 dark:text-amber-400" aria-label="needs attention" />,
  error: <XCircle className="size-4 text-destructive" aria-label="error" />,
  off: <CircleDashed className="size-4 text-muted-foreground" aria-label="off" />,
}

export function ConnectionsCard() {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ["status-connections"],
    queryFn: () => api.get<ConnectionsView>("status/connections"),
    refetchInterval: 60_000,
  })
  const refresh = async () => {
    const fresh = await api.get<ConnectionsView>("status/connections?refresh=true")
    qc.setQueryData(["status-connections"], fresh)
  }
  return (
    <Card className="md:col-span-2">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="grid gap-1.5">
          <CardTitle>Connections</CardTitle>
          <CardDescription>
            Apps and services RuTrackarr works with{q.data ? ` · checked ${formatAgo(q.data.checked_at)}` : ""}
          </CardDescription>
        </div>
        <Button variant="ghost" size="sm" onClick={refresh} disabled={q.isFetching} aria-label="Check again">
          <RefreshCw className={q.isFetching ? "animate-spin" : ""} />
        </Button>
      </CardHeader>
      <CardContent>
        {q.isPending && <p className="text-sm text-muted-foreground">checking…</p>}
        {q.error && <p className="text-sm text-destructive">Could not load: {q.error.message}</p>}
        {q.data && (
          <ul className="grid gap-3 sm:grid-cols-2">
            {q.data.items.map((c) => (
              <li key={c.id} className="grid gap-0.5 text-sm">
                <div className="flex items-center gap-2">
                  {ICON[c.state]}
                  <span className="font-medium">{c.name}</span>
                  {c.version && <span className="text-xs text-muted-foreground">{c.version}</span>}
                </div>
                {c.detail && <span className="pl-6 text-muted-foreground">{c.detail}</span>}
                {c.checks.length > 0 && (
                  <ul className="grid gap-0.5 pl-6">
                    {c.checks.map((ch) => (
                      <li key={ch.label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        {ch.ok ? (
                          <CheckCircle2 className="size-3 text-emerald-600 dark:text-emerald-400" />
                        ) : (
                          <XCircle className="size-3 text-destructive" />
                        )}
                        {ch.label}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
