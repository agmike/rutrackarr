import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, XCircle } from "lucide-react"
import { api, formatAgo, type AlertsView } from "@/lib/api"

/** What's wrong right now, on every page (also sent through Apprise when configured). */
export function AlertBanner() {
  const q = useQuery({ queryKey: ["alerts"], queryFn: () => api.get<AlertsView>("alerts"), refetchInterval: 30_000 })
  const items = q.data?.items ?? []
  if (items.length === 0) return null
  return (
    <div className="mb-4 grid gap-1.5" role="alert">
      {items.map((a) => (
        <div
          key={a.key}
          className={
            a.level === "error"
              ? "flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm"
              : "flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm"
          }
        >
          {a.level === "error" ? (
            <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
          ) : (
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
          )}
          <span className="min-w-0 flex-1 break-words">{a.message}</span>
          <span className="shrink-0 text-xs text-muted-foreground">since {formatAgo(a.since)}</span>
        </div>
      ))}
    </div>
  )
}
