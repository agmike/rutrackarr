# RuTrackarr

A Torznab indexer for [RuTracker](https://rutracker.org) built for Sonarr and Radarr, with
language-aware release ranking — plus a qBittorrent-compatible download client that makes RuTracker
releases import like any other, and tracked topics that follow RuTracker's updating releases.

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
  with tokens they can't misread (scored by the custom formats in `docs/`);
- as a **download client** in front of qBittorrent, tags the downloaded files so Sonarr scores an
  import like the grab, and keeps RuTracker's one-torrent-per-topic model working with Sonarr's
  per-episode grabs;
- **tracks topics**: RuTracker updates a topic (new episodes) by replacing its torrent; RuTrackarr
  applies the new one in place, so only new files download;
- has a web UI for settings, a status page, searches (raw, or simulated as Sonarr/Radarr), the
  query log, tracked topics and overrides, with alerts through Apprise.

## Running

Container image: `ghcr.io/agmike/rutrackarr` (runs as a non-root user; mount a volume at `/data`).
Configuration is done in the web UI (default port `8787`). Optional environment variables:
`RUTRACKARR_URL_BASE` (e.g. `/rutrackarr` behind a reverse proxy), `RUTRACKARR_SECRET_KEY`,
`RUTRACKARR_API_KEY` (pins the API key, e.g. from a secret store).

You need your own RuTracker account; please respect the tracker's rules and keep request
rates low. A [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) instance is used
the way it is intended: when Cloudflare challenges a request, RuTrackarr has FlareSolverr's
browser fetch that page instead (and keeps doing so for a while). Note: through FlareSolverr
the login form is submitted as UTF-8, so a RuTracker username or password with non-Latin
characters may not work while requests go through FlareSolverr.

### Companion tracks and fonts (Sonarr/Radarr custom script)

`contrib/sonarr/rutrackarr-companions.sh` (works in both Sonarr and Radarr) links a torrent's
external audio and subtitles next to each imported episode or film under Jellyfin/Plex/Kodi names. With `RUTRACKARR_FONTS_DIR` set it also
links the torrent's fonts into one shared folder (named by content, so nothing collides). Point
Jellyfin's *fallback fonts* (Dashboard → Playback → Transcoding) at it so the web player renders
ASS subtitles in their intended fonts. Note that the web player loads every font in that folder
for each video with ASS subtitles, and that other clients don't use it.

### Download client (optional, recommended for Sonarr)

Sonarr scores a grab by its release title but an import by the file names, and RuTracker file
names say nothing about the voice-over or subtitles — so a release that won the search can
score low, or be rejected, on import. RuTrackarr can stand in front of your qBittorrent:

1. In RuTrackarr → Settings → *Download client*, connect it to qBittorrent: either its Web UI
   (URL + login) or a [qui](https://github.com/autobrr/qui) client proxy (qui URL + the proxy
   token, kept secret).
2. In Sonarr/Radarr add a **qBittorrent** download client: host and port of RuTrackarr, URL
   base `<RuTrackarr URL base>/qbit` (e.g. `/rutrackarr/qbit`), the RuTrackarr **API key** in
   its *API key* field (username empty), and a category of its own (e.g. `sonarr/rutracker`,
   with the save path of your usual category). Optionally a post-import category
   (`sonarr/completed`).
3. Edit the RuTrackarr indexer and select that download client.

Torrents grabbed from RuTrackarr then go through it: the topic is added to qBittorrent
stopped, its video files get the release's language tags appended (`… OrigAudio RusSubs
RTA-T1 -RuTracker.mkv`), and then it starts. Everything else is passed through unchanged.
Each grab is its own download in Sonarr (several grabs of one topic share one torrent), and
finished downloads are reported as still seeding, so files are hardlinked or copied, never
moved away from a torrent that keeps seeding. With a post-import category set, the topic's
torrent moves there once all its releases have (and back when a new release of it is grabbed).

RuTracker series topics are usually whole seasons, growing as episodes come out. For a single-
episode search RuTrackarr also offers the episode on its own (`Show S01E05 …`), when it can tell
which file of the topic it is (from the file names, or their order); Sonarr then sees a download
of just that file. With *Download only the grabbed episode* on (Settings → Download client),
qBittorrent downloads only that file (plus its external audio, subtitles and fonts) — the rest of
the topic downloads when other episodes are grabbed.

Use categories that don't contain each other: in qBittorrent 5.2 a category also lists its
subcategories, so e.g. `sonarr/default`, `sonarr/rutracker`, `sonarr/completed` — not `sonarr`
and `sonarr/rutracker`.

### Custom formats

Release names carry tokens for Sonarr/Radarr custom formats (importable into
[Clonarr](https://github.com/prophetse7en/clonarr) or the apps directly):
`docs/arr-custom-formats.json` — language tiers `RTA-T1` (original + subtitles) … `RTA-T9`
(languages not stated), Russian voice types, and `RTA-QC` (QC subsections, give it a small
negative score); `docs/arr-custom-formats-ru-first.json` — for Russian-voice-first profiles;
`docs/arr-custom-formats-language.json` — a language block for profiles that accept original,
Russian or English audio.
The token format is described in `docs/title-format.md`.

### Web UI

- **Status:** service (version, uptime, query stats, RuTracker request budget), RuTracker session,
  downloads, tracked topics, recent grabs, activity, queries, and connections (incl. whether
  Sonarr/Radarr are set up to use RuTrackarr).
- **Search**, two modes — *RuTracker*: a plain search, every result parsed and ranked (and
  trackable); *As Sonarr/Radarr*: run the exact search Sonarr/Radarr would send for a series or film from their
  libraries (season/episode), with or without overrides, and see every RuTracker topic with its
  release name or why it was dropped.
- **Queries:** the query log — each search with the topics it found and why each was kept or
  dropped; searches without results; dropped topics (unparsed titles, other series…).
- **Tracked:** RuTracker topics RuTrackarr follows — tracked by hand (from Search or a topic URL:
  downloaded right away into their own qBittorrent category, e.g. `rutrackarr/tracked`, that no
  Sonarr/Radarr client asks for) or because Sonarr/Radarr grabbed them. Tracked topics take part
  in every Sonarr/Radarr search; a grab of one reuses the torrent that's already there. A tracked
  topic that has the episode asked for answers the search without RuTracker being asked, and after
  an update its newest episodes show up in Sonarr's RSS on their own, so Sonarr grabs new episodes
  of an airing series without searching. Grabbed topics follow the series/film (checked every 6 hours): paused
  (no update checks) while it isn't monitored in Sonarr/Radarr, untracked when it's deleted there
  or nothing the topic covers is left in the library (unless it's still downloading); topics
  tracked by hand are left alone. To have this happen right after a deletion, add a **Webhook**
  connection in Sonarr/Radarr (Settings → Connect) with *On Series/Movie Delete* and *On
  Episode/Movie File Delete*, URL `<RuTrackarr>/api/tracked/library-event?apikey=<API key>`. A topic that RuTracker merges into another one (a new season pack
  replacing the episodes) needs nothing special: the new topic is found and grabbed episode by episode. Remove
  deletes the torrent (imported episodes stay: hardlinks) and takes unfinished releases out of
  Sonarr's/Radarr's queue. Updates are found through RuTracker's per-section feeds (plus a slow
  per-topic check) and applied in place: the new torrent takes the old one's folder, category
  and file names, so a recheck finds what's downloaded and only new or changed files download.
- **Overrides:** per series/film (TVDB id / TMDb id): extra or replacement search titles, the
  release title, a season offset, include/exclude title filters, and topics pinned to the series
  (and a season). JSON export/import.
- **Alerts:** RuTracker failing or back, FlareSolverr/qBittorrent unreachable, repeated failed
  searches, topic torrents removed — shown as a banner and sent through
  [Apprise](https://github.com/caronc/apprise/wiki) (Telegram, ntfy, Discord, email, webhooks…).

## Security

**RuTrackarr has no built-in login.** Anyone who can reach its web UI can read and change
its settings (stored secrets are never shown, but they can be replaced). Do not expose it
directly to the internet: keep it on a private network, or put it behind a reverse proxy
that does authentication (for example an SSO/forward-auth proxy). The Torznab endpoint and the
download client API used by Sonarr/Radarr are protected by the API key.

Secrets (RuTracker password, API keys, TMDb token, the qBittorrent password or qui proxy token,
Apprise URLs) are encrypted at rest with a key from `RUTRACKARR_SECRET_KEY`, or — when that is
unset — a key generated into `/data/secret.key`. RuTrackarr never stores `.torrent` files (they
carry your passkey); it keeps only their info hash and file list.

## Development

- `backend/` — Python 3.13, FastAPI, SQLite + Alembic (`uv sync`, `uv run pytest`,
  `uv run ruff check .`, `uv run ruff format .`)
- `frontend/` — React + Vite + Tailwind + shadcn/ui (`npm ci`, `npm run dev`, `npm run build`,
  `npx oxlint`)
- Releases: pushing a `vX.Y.Z` tag builds `ghcr.io/agmike/rutrackarr:X.Y.Z` (version and commit
  shown in the UI); `main` builds `:edge`.

## License

MIT
