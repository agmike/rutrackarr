import { useQuery } from "@tanstack/react-query"
import { ApiKeyCard } from "@/components/ApiKeyCard"
import { type FieldSpec, SettingsSection } from "@/components/SettingsSection"
import { api, type SettingsView } from "@/lib/api"

const rutracker: FieldSpec[] = [
  { key: "rutracker.username", label: "Username", type: "text" },
  { key: "rutracker.password", label: "Password", type: "secret" },
  {
    key: "rutracker.base_url",
    label: "Site address",
    type: "url",
    help: "Main site or a mirror, e.g. https://rutracker.org or https://rutracker.net.",
  },
  {
    key: "rutracker.requests_per_minute",
    label: "Max requests per minute",
    type: "number",
    help: "Keep this low — bursts of requests can trigger a login captcha.",
  },
]

const flaresolverr: FieldSpec[] = [
  { key: "flaresolverr.url", label: "FlareSolverr URL", type: "url", placeholder: "http://flaresolverr:8191/" },
  { key: "flaresolverr.timeout_seconds", label: "Timeout (seconds)", type: "number" },
]

const metadata: FieldSpec[] = [
  {
    key: "tmdb.read_access_token",
    label: "TMDb API Read Access Token",
    type: "secret",
    help: (
      <>
        From themoviedb.org → Settings → API (the long “API Read Access Token”). Used to look up Russian,
        original and English titles by ID.
      </>
    ),
  },
]

const arr: FieldSpec[] = [
  { key: "sonarr.url", label: "Sonarr URL", type: "url", placeholder: "http://sonarr:8989" },
  { key: "sonarr.api_key", label: "Sonarr API key", type: "secret" },
  { key: "radarr.url", label: "Radarr URL", type: "url", placeholder: "http://radarr:7878" },
  { key: "radarr.api_key", label: "Radarr API key", type: "secret" },
]

const general: FieldSpec[] = [
  { key: "general.query_log_retention_days", label: "Keep query log for (days)", type: "number" },
]

export function SettingsPage() {
  const { data, error, isPending } = useQuery({ queryKey: ["settings"], queryFn: () => api.get<SettingsView>("settings") })
  if (isPending) return <p className="text-muted-foreground">Loading…</p>
  if (error || !data) return <p className="text-destructive">Could not load settings: {error?.message}</p>
  return (
    <div className="grid max-w-3xl gap-6">
      <section id="rutracker">
        <SettingsSection title="RuTracker" description="Your RuTracker account." fields={rutracker} view={data} />
      </section>
      <section id="flaresolverr">
        <SettingsSection
          title="FlareSolverr"
          description="Solves Cloudflare's browser check in front of RuTracker."
          fields={flaresolverr}
          view={data}
        />
      </section>
      <section id="metadata">
        <SettingsSection title="Metadata" fields={metadata} view={data} />
      </section>
      <section id="api-key">
        <ApiKeyCard />
      </section>
      <section id="arr">
        <SettingsSection
          title="Sonarr & Radarr"
          description="Optional. Used for series/movie lookups and to show what Sonarr/Radarr grabbed."
          fields={arr}
          view={data}
        />
      </section>
      <section id="general">
        <SettingsSection title="General" fields={general} view={data} />
      </section>
    </div>
  )
}
