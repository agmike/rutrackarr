import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router"
import { StatTile } from "@/components/StatTile"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api, formatAgo, type TrackingView } from "@/lib/api"

export function TrackingCard() {
  const q = useQuery({ queryKey: ["status-tracking"], queryFn: () => api.get<TrackingView>("status/tracking"), refetchInterval: 30_000 })
  const s = q.data
  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle>Tracked topics</CardTitle>
        <CardDescription>
          Topics RuTrackarr follows for updates ·{" "}
          <Link to="/tracked" className="underline">
            manage
          </Link>
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {q.error && <p className="text-destructive">Could not load: {q.error.message}</p>}
        {s && (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <StatTile
                label="Tracked"
                value={s.manual + s.grabbed}
                hint={`${s.manual} by hand, ${s.grabbed} grabbed by Sonarr/Radarr${s.auto_track ? "" : " (auto-track off)"}${s.gone ? `, ${s.gone} gone` : ""}`}
              />
              <StatTile label="Updated, 7 days" value={s.updated_7d} hint={s.last_change ? `last ${formatAgo(s.last_change)}` : "no updates yet"} />
              <StatTile label="Feeds read" value={s.feeds_at ? formatAgo(s.feeds_at) : "—"} hint="RuTracker's section feeds, for updates" />
              <StatTile label="Checks due" value={s.due} hint="Per-topic checks waiting (a couple run each minute)" />
            </div>
            {s.feeds.length > 0 && (
              <ul className="grid gap-0.5 text-xs text-muted-foreground">
                {s.feeds.map((f) => (
                  <li key={f.forum_id}>
                    {f.forum || `section ${f.forum_id}`}: {f.tracked} tracked ·{" "}
                    {f.error ? (
                      <span className="text-destructive">{f.error}</span>
                    ) : f.status === 200 ? (
                      `feed OK, ${f.entries} recent topics`
                    ) : (
                      <span className="text-destructive">feed HTTP {f.status}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {(s.errors.length > 0 || s.failed_7d > 0) && (
              <ul className="grid gap-0.5 text-xs text-destructive">
                {s.failed_7d > 0 && <li>{s.failed_7d} failed updates in 7 days (see Activity)</li>}
                {s.errors.map((e) => (
                  <li key={e.topic_id}>
                    {e.title}: {e.error}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
