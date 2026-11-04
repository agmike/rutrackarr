import { useQuery } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { apiGet, type SystemStatus } from "@/lib/api"

export function StatusPage() {
  const { data, error, isPending } = useQuery({
    queryKey: ["system-status"],
    queryFn: () => apiGet<SystemStatus>("system/status"),
  })
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Service</CardTitle>
          <CardDescription>rutrackarr backend</CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-2 text-sm">
          {isPending && <span className="text-muted-foreground">checking…</span>}
          {error && <Badge variant="destructive">unreachable</Badge>}
          {data && (
            <>
              <Badge>online</Badge>
              <span className="text-muted-foreground">version {data.version}</span>
            </>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>RuTracker</CardTitle>
          <CardDescription>Session and Cloudflare state</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">Not configured yet — see Settings.</CardContent>
      </Card>
    </div>
  )
}
