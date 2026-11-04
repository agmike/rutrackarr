import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, CircleDashed } from "lucide-react"
import { Link } from "react-router"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, type SettingsView, type SystemStatus } from "@/lib/api"

export function StatusPage() {
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => api.get<SystemStatus>("system/status") })
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.get<SettingsView>("settings") })
  const s = settings.data
  const checks = s
    ? [
        {
          label: "RuTracker account",
          ok: !!s.values["rutracker.username"] && s.secrets["rutracker.password"],
          to: "settings#rutracker",
        },
        { label: "FlareSolverr", ok: !!s.values["flaresolverr.url"], to: "settings#flaresolverr" },
        { label: "TMDb token", ok: s.secrets["tmdb.read_access_token"], to: "settings#metadata" },
      ]
    : []
  return (
    <div className="grid max-w-3xl gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Service</CardTitle>
          <CardDescription>rutrackarr backend</CardDescription>
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
          <CardTitle>Configuration</CardTitle>
          <CardDescription>What still needs setting up</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm">
          {checks.map((c) => (
            <Link key={c.label} to={c.to} className="flex items-center gap-2 hover:underline">
              {c.ok ? (
                <CheckCircle2 className="size-4 text-emerald-500" />
              ) : (
                <CircleDashed className="text-muted-foreground size-4" />
              )}
              {c.label}
              <span className="text-muted-foreground">{c.ok ? "configured" : "not configured"}</span>
            </Link>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
