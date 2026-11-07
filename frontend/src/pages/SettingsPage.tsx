import { useQuery } from "@tanstack/react-query"
import { ApiKeyCard } from "@/components/ApiKeyCard"
import {
  AlertsTest,
  ArrConnectionTests,
  FlareSolverrTest,
  QbittorrentTest,
  RuTrackerSessionPanel,
} from "@/components/RuTrackerSessionPanel"
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
    help: "Limit for all requests to RuTracker — searches, downloads and logins. Sonarr can send many searches at once; keeping this low avoids throttling and extra Cloudflare checks. (Login captchas mostly come from repeated logins, which RuTrackarr avoids by keeping its session.)",
  },
]

const search: FieldSpec[] = [
  {
    key: "search.cache_minutes",
    label: "Keep search results for (minutes)",
    type: "number",
    help: "Sonarr repeats the same search for every episode, title and search type — an anime season search can take 15 minutes. Results are reused for this long, so each RuTracker search runs once. 0 turns the cache off.",
  },
  {
    key: "search.rss_cache_minutes",
    label: "Keep the newest-releases feed for (minutes)",
    type: "number",
    help: "Sonarr/Radarr RSS sync (a search without a query). Keep it short so new topics are picked up quickly.",
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
  { key: "sonarr.url", label: "Sonarr URL", type: "url" },
  { key: "sonarr.api_key", label: "Sonarr API key", type: "secret" },
  { key: "radarr.url", label: "Radarr URL", type: "url" },
  { key: "radarr.api_key", label: "Radarr API key", type: "secret" },
]

const isQui = (v: Record<string, string>) => v["qbittorrent.mode"] === "qui"
const qbittorrent: FieldSpec[] = [
  {
    key: "qbittorrent.mode",
    label: "Connect through",
    type: "select",
    options: [
      { value: "qbittorrent", label: "qBittorrent Web UI (URL + login)" },
      { value: "qui", label: "qui client proxy (qui URL + proxy token)" },
    ],
  },
  {
    key: "qbittorrent.url",
    label: "qBittorrent URL",
    type: "url",
    placeholder: "http://qbittorrent:8080",
    help: "qBittorrent's Web UI. Leave empty to serve RuTracker's .torrent files unchanged.",
    showIf: (v) => !isQui(v),
  },
  { key: "qbittorrent.username", label: "Username", type: "text", showIf: (v) => !isQui(v) },
  { key: "qbittorrent.password", label: "Password", type: "secret", showIf: (v) => !isQui(v) },
  {
    key: "qui.url",
    label: "qui URL",
    type: "url",
    placeholder: "http://qui:7476",
    help: "Where RuTrackarr reaches qui (no /proxy/… part).",
    showIf: isQui,
  },
  {
    key: "qui.token",
    label: "Proxy token",
    type: "secret",
    placeholder: "The part after /proxy/ of the client-proxy URL qui shows",
    help: "Create a client proxy for RuTrackarr in qui; its URL ends in /proxy/<token>. Kept like a password.",
    showIf: isQui,
  },
]

const tracking: FieldSpec[] = [
  {
    key: "tracking.auto_track",
    label: "Track what Sonarr/Radarr grab",
    type: "select",
    options: [
      { value: "on", label: "On — follow updates of every grabbed topic" },
      { value: "off", label: "Off — only topics tracked by hand" },
    ],
  },
  {
    key: "tracking.category",
    label: "qBittorrent category for topics tracked by hand",
    type: "text",
    placeholder: "rutrackarr/tracked",
    help: "Create it in qBittorrent/qui (with a save path) — RuTrackarr can't through qui's proxy. Use one no Sonarr/Radarr download client asks for: not a parent or child of their categories.",
  },
  {
    key: "tracking.feed_minutes",
    label: "Read RuTracker's section feeds every (minutes)",
    type: "number",
    help: "One request per section that has tracked topics; topics the feed shows as changed are then checked.",
  },
  {
    key: "tracking.check_hours",
    label: "Also check each ongoing topic every (hours)",
    type: "number",
    help: "A backstop for updates the feeds miss: one request per topic. Finished topics are checked 7× less often.",
  },
]

const alerts: FieldSpec[] = [
  {
    key: "alerts.apprise_urls",
    label: "Apprise URLs",
    type: "secret",
    placeholder: "tgram://<bot token>/<chat id>  ntfy://ntfy.sh/<topic>",
    help: (
      <>
        Where alerts go — one or more{" "}
        <a className="underline" href="https://github.com/caronc/apprise/wiki" target="_blank" rel="noreferrer">
          Apprise URLs
        </a>
        , separated by spaces: Telegram, ntfy, Discord, Gotify, email, a JSON webhook… Sent when RuTracker fails or comes
        back, FlareSolverr or qBittorrent stop answering, searches keep failing, or a topic torrent disappears. Active
        problems also show as a banner on every page.
      </>
    ),
  },
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
        <SettingsSection title="RuTracker" description="Your RuTracker account." fields={rutracker} view={data}>
          <RuTrackerSessionPanel />
        </SettingsSection>
      </section>
      <section id="search">
        <SettingsSection
          title="Search"
          description="How RuTrackarr answers Sonarr and Radarr."
          fields={search}
          view={data}
        />
      </section>
      <section id="flaresolverr">
        <SettingsSection
          title="FlareSolverr"
          description="Solves Cloudflare's browser check in front of RuTracker."
          fields={flaresolverr}
          view={data}
        >
          {(pending) => <FlareSolverrTest pending={pending} />}
        </SettingsSection>
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
          description="Optional. Used for series/movie lookups and to show what Sonarr/Radarr grabbed. Include the URL base, e.g. http://sonarr:8989/sonarr."
          fields={arr}
          view={data}
        >
          {(pending) => <ArrConnectionTests pending={pending} />}
        </SettingsSection>
      </section>
      <section id="download-client">
        <SettingsSection
          title="Download client"
          description="RuTrackarr as a qBittorrent for Sonarr and Radarr: RuTracker topics are added to the real qBittorrent with their video files renamed to carry the release's language tags, so imported files score like the grab. In Sonarr/Radarr add a qBittorrent download client with host and port of RuTrackarr, URL base <url base>/qbit, the RuTrackarr API key in its API key field (username empty), and a category of its own that isn't a parent or child of another client's (e.g. sonarr/rutracker next to sonarr/default); then pick it as the RuTrackarr indexer's download client."
          fields={qbittorrent}
          view={data}
        >
          {(pending) => (
            <div className="grid gap-3">
              {pending["qbittorrent.mode"] === "qui" && (
                <p className="text-sm text-muted-foreground">
                  RuTrackarr uses{" "}
                  <code className="break-all">
                    {(pending["qui.url"] || "http://qui:7476").replace(/\/+$/, "")}/proxy/
                    {pending["qui.token"] || data.secrets["qui.token"] ? "••••••••" : "<token>"}
                  </code>
                </p>
              )}
              <QbittorrentTest pending={pending} />
            </div>
          )}
        </SettingsSection>
      </section>
      <section id="tracking">
        <SettingsSection title="Tracked topics" fields={tracking} view={data} />
      </section>
      <section id="alerts">
        <SettingsSection title="Alerts" description="Notifications through Apprise." fields={alerts} view={data}>
          {(pending) => <AlertsTest pending={pending} />}
        </SettingsSection>
      </section>
      <section id="general">
        <SettingsSection title="General" fields={general} view={data} />
      </section>
    </div>
  )
}
