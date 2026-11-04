import { CheckCircle2, CircleDashed, X } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { SettingsView } from "@/lib/api"

type Item = { id: string; label: string; ok: boolean; optional: boolean; to: string }

const DISMISS_KEY = "rutrackarr.setup.dismissed"

function readDismissed(): string | null {
  try {
    return localStorage.getItem(DISMISS_KEY)
  } catch {
    return null
  }
}

export function SetupChecklist({ settings }: { settings: SettingsView }) {
  const v = settings.values
  const sec = settings.secrets
  const items: Item[] = [
    {
      id: "rutracker",
      label: "RuTracker account",
      ok: !!v["rutracker.username"] && sec["rutracker.password"],
      optional: false,
      to: "settings#rutracker",
    },
    { id: "flaresolverr", label: "FlareSolverr", ok: !!v["flaresolverr.url"], optional: false, to: "settings#flaresolverr" },
    { id: "tmdb", label: "TMDb token", ok: sec["tmdb.read_access_token"], optional: false, to: "settings#metadata" },
    { id: "sonarr", label: "Sonarr connection", ok: sec["sonarr.api_key"], optional: true, to: "settings#arr" },
    { id: "radarr", label: "Radarr connection", ok: sec["radarr.api_key"], optional: true, to: "settings#arr" },
  ]
  const missing = items.filter((i) => !i.ok)
  const requiredMissing = missing.some((i) => !i.optional)
  // Dismissal is remembered per browser for the current set of missing optional items;
  // if a different item goes missing later, the card comes back.
  const signature = missing.map((i) => i.id).join(",")
  const [dismissed, setDismissed] = useState(readDismissed)

  if (missing.length === 0) return null
  if (!requiredMissing && dismissed === signature) return null

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="grid gap-1.5">
          <CardTitle>Setup</CardTitle>
          <CardDescription>{requiredMissing ? "What still needs setting up" : "Only optional items left"}</CardDescription>
        </div>
        {!requiredMissing && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              try {
                localStorage.setItem(DISMISS_KEY, signature)
              } catch {
                /* private mode: dismiss for this page view only */
              }
              setDismissed(signature)
            }}
          >
            <X /> Dismiss
          </Button>
        )}
      </CardHeader>
      <CardContent className="grid gap-2 text-sm">
        {items.map((i) => (
          <Link key={i.id} to={i.to} className="flex items-center gap-2 hover:underline">
            {i.ok ? (
              <CheckCircle2 className="size-4 text-emerald-500" />
            ) : (
              <CircleDashed className="text-muted-foreground size-4" />
            )}
            {i.label}
            {i.optional && (
              <Badge variant="outline" className="text-xs">
                optional
              </Badge>
            )}
            <span className="text-muted-foreground">{i.ok ? "configured" : "not configured"}</span>
          </Link>
        ))}
      </CardContent>
    </Card>
  )
}
