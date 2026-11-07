# RuTrackarr

A Torznab indexer for [RuTracker](https://rutracker.org) built for Sonarr and Radarr,
with language-aware release ranking.

> [!WARNING]
> **Early development — not ready for use.**
>
> - This is a personal project, built for my own homelab first. The code is **largely
>   written with an AI coding assistant (Claude)** and reviewed by me; I am not a web
>   developer. Expect rough edges, breaking changes and bugs — use at your own risk.
> - It is **not affiliated with RuTracker**, Sonarr, Radarr, Prowlarr or Jackett. You need
>   your own RuTracker account and are responsible for following the tracker's rules.
> - No warranty of any kind (see [LICENSE](LICENSE)). Issues and suggestions are welcome,
>   but support is best-effort.

## Why

Prowlarr and Jackett shape RuTracker results for Sonarr's limits — Prowlarr, for example,
removes subtitle information from release titles, because Sonarr would mistake subtitle
languages for audio languages. RuTrackarr instead works from the raw RuTracker titles:

- searches RuTracker by **series/movie IDs**, using the Russian, original and English titles;
- parses each release into audio tracks (dub / multi-voice / single-voice, studio), original
  track, **subtitle languages**, episode range and quality;
- ranks releases against your **language preferences** and hands Sonarr/Radarr titles
  with tokens they can't misread;
- has a web UI for settings, overrides, a query log and test searches.

## Running

Container image: `ghcr.io/agmike/rutrackarr` (runs as a non-root user; mount a volume at `/data`).
Configuration is done in the web UI (default port `8787`). Optional environment variables:
`RUTRACKARR_URL_BASE` (e.g. `/rutrackarr` behind a reverse proxy), `RUTRACKARR_SECRET_KEY`,
`RUTRACKARR_API_KEY`.

You need your own RuTracker account; please respect the tracker's rules and keep request
rates low. A [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) instance is used
the way it is intended: when Cloudflare challenges a request, RuTrackarr has FlareSolverr's
browser fetch that page instead (and keeps doing so for a while). Note: through FlareSolverr
the login form is submitted as UTF-8, so a RuTracker username or password with non-Latin
characters may not work while requests go through FlareSolverr.

### Download client (optional, recommended for Sonarr)

Sonarr scores a grab by its release title but an import by the file names, and RuTracker file
names say nothing about the voice-over or subtitles — so a release that won the search can
score low, or be rejected, on import. RuTrackarr can stand in front of your qBittorrent:

1. In RuTrackarr → Settings → *Download client*, enter the qBittorrent Web UI URL and login.
2. In Sonarr/Radarr add a **qBittorrent** download client: host and port of RuTrackarr, URL
   base `<RuTrackarr URL base>/qbit` (e.g. `/rutrackarr/qbit`), any username, the RuTrackarr
   **API key as password**, and a category of its own (e.g. `sonarr-rutracker`; give it the
   same save path as your usual category in qBittorrent).
3. Edit the RuTrackarr indexer and select that download client.

Torrents grabbed from RuTrackarr then go through it: the topic is added to qBittorrent
stopped, its video files get the release's language tags appended (`… OrigAudio RusSubs
RTA-T1 -RuTracker.mkv`), and then it starts. Everything else is passed through unchanged.
Each grab is its own download in Sonarr (several grabs of one topic share one torrent), and
finished downloads are reported as still seeding, so files are hardlinked or copied, never
moved away from a torrent that keeps seeding.

## Security

**RuTrackarr has no built-in login.** Anyone who can reach its web UI can read and change
its settings (stored secrets are never shown, but they can be replaced). Do not expose it
directly to the internet: keep it on a private network, or put it behind a reverse proxy
that does authentication (for example an SSO/forward-auth proxy). The Torznab endpoint used
by Sonarr/Radarr is protected by its API key.

Secrets (RuTracker password, API keys, TMDb token) are encrypted at rest with a key from
`RUTRACKARR_SECRET_KEY`, or — when that is unset — a key generated into `/data/secret.key`.

## Development

- `backend/` — Python 3.13, FastAPI (`uv sync`, `uv run pytest`, `uv run ruff check .`)
- `frontend/` — React + Vite + Tailwind + shadcn/ui (`npm ci`, `npm run dev`, `npm run build`)

## License

MIT
