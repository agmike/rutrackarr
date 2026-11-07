import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useRuTrackerSession } from "@/components/RuTrackerSessionPanel"
import { ConnectionsCard } from "@/components/ConnectionsCard"
import { DownloadsCard } from "@/components/DownloadsCard"
import { RecentGrabsCard } from "@/components/RecentGrabsCard"
import { SetupChecklist } from "@/components/SetupChecklist"
import { api, formatWhen, type SettingsView, type SystemStatus } from "@/lib/api"

export function StatusPage() {
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => api.get<SystemStatus>("system/status") })
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<SettingsView>("settings") })
  const session = useRuTrackerSession().data
  return (
    <div className="grid max-w-4xl gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Service</CardTitle>
          <CardDescription>RuTrackarr backend</CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-2 text-sm">
          {status.isPending && <span className="text-muted-foreground">checking…</span>}
          {status.error && <Badge variant="destructive">unreachable</Badge>}
          {status.data && (
            <>
              <Badge>online</Badge>
              <span className="text-muted-foreground">version {status.data.version}</span>
            </>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>RuTracker session</CardTitle>
          <CardDescription>Login and Cloudflare state</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-1 text-sm">
          <div className="flex items-center gap-2">
            {session?.has_session && session.username ? (
              <Badge>logged in as {session.username}</Badge>
            ) : (
              <Badge variant="outline">not logged in</Badge>
            )}
          </div>
          <span className="text-muted-foreground">Last successful request: {formatWhen(session?.last_ok_at ?? null)}</span>
          <span className="text-muted-foreground">Cloudflare check passed: {formatWhen(session?.cf_solved_at ?? null)}</span>
          {session?.last_error && <span className="text-destructive">Last error: {session.last_error}</span>}
        </CardContent>
      </Card>
      {settings.data && <SetupChecklist settings={settings.data} />}
      <DownloadsCard />
      <ConnectionsCard />
      <RecentGrabsCard />
    </div>
  )
}
