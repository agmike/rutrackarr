import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RefreshCw } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, errorMessage, formatAgo, formatWhen, type RuTrackerSession } from "@/lib/api"

export function SessionCard() {
  const qc = useQueryClient()
  // Refreshed regularly: the background check may clear an error while the page is open.
  const session = useQuery({
    queryKey: ["rutracker-session"],
    queryFn: () => api.get<RuTrackerSession>("rutracker/session"),
    refetchInterval: 30_000,
  }).data
  const check = useMutation({
    mutationFn: () => api.post<{ logged_in: boolean; username: string | null }>("rutracker/check"),
    onSuccess: (r) => (r.logged_in ? toast.success(`RuTracker OK — logged in as ${r.username}`) : toast.warning("RuTracker answers, but the session is logged out")),
    onError: (e) => toast.error(errorMessage(e)),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["rutracker-session"] })
      qc.invalidateQueries({ queryKey: ["status-events"] })
    },
  })
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="grid gap-1.5">
          <CardTitle>RuTracker session</CardTitle>
          <CardDescription>Login and Cloudflare state</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => check.mutate()} disabled={check.isPending}>
          <RefreshCw className={check.isPending ? "animate-spin" : ""} />
          Check now
        </Button>
      </CardHeader>
      <CardContent className="grid gap-1 text-sm">
        <div className="flex items-center gap-2">
          {session?.has_session && session.username ? (
            <Badge>logged in as {session.username}</Badge>
          ) : (
            <Badge variant="outline">not logged in</Badge>
          )}
          {session?.last_error && <Badge variant="destructive">failing</Badge>}
        </div>
        <span className="text-muted-foreground" title={formatWhen(session?.last_ok_at ?? null)}>
          Last successful request: {formatAgo(session?.last_ok_at ?? null)}
        </span>
        <span className="text-muted-foreground" title={formatWhen(session?.cf_solved_at ?? null)}>
          Cloudflare check passed: {formatAgo(session?.cf_solved_at ?? null)}
        </span>
        {session?.last_error && (
          <span className="text-destructive">
            {session.last_error}
            <span className="block text-xs text-muted-foreground">Checked again every 5 minutes until RuTracker answers.</span>
          </span>
        )}
      </CardContent>
    </Card>
  )
}
