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
