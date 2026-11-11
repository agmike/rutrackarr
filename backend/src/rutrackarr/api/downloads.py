"""Downloads page: what RuTrackarr manages in qBittorrent right now.

- releases grabbed through the download client that Sonarr/Radarr haven't finished with yet
  (still in their queue: downloading, or waiting for import);
- every tracked topic's torrent (grabbed or by hand), whatever its state.

One entry per topic torrent (several releases can share one). Once a release is imported and its
topic isn't tracked, it's no longer RuTrackarr's business (Sonarr's post-import category, then
whatever cleans up there) and drops off this list.
"""

from typing import Any

from fastapi import APIRouter, Request

from rutrackarr.api.status import _status
from rutrackarr.qbit.upstream import QbitError
from rutrackarr.torznab.downloads import Download
from rutrackarr.tracking.tracker import Tracked, queued

router = APIRouter(prefix="/downloads", tags=["downloads"])

FIELDS = (
    "state", "progress", "size", "dlspeed", "upspeed", "eta", "ratio", "uploaded", "downloaded",
    "num_seeds", "num_leechs", "category",
)  # fmt: skip
ORDER = {"downloading": 0, "stalled": 1, "queued": 2, "stopped": 3, "error": 4, "seeding": 5}


def app_of(category: str | None) -> str:
    return "radarr" if (category or "").lower().startswith(("radarr", "movie")) else "sonarr"


@router.get("")
async def managed(request: Request) -> dict[str, Any]:
    qbit = request.app.state.qbit
    if not qbit.configured():
        return {"configured": False, "error": None, "items": [], "totals": None}
    store, tracker = request.app.state.downloads, request.app.state.tracker
    settings, transport = request.app.state.settings_service, request.app.state.http_transport
    client = request.app.state.rutracker

    releases = [d for d in store.active() if d.real_hash]
    queues: dict[str, set[str] | None] = {
        app: await queued(settings, app, transport) for app in ("sonarr", "radarr")
    }

    def in_queue(d: Download) -> bool | None:
        q = queues[app_of(d.category)]
        return None if q is None else d.info_hash.upper() in q

    tracked: dict[str, Tracked] = {
        t.info_hash: t for t in tracker.all(include_gone=False) if t.info_hash
    }
    # Topic torrent → its releases that are RuTrackarr's business.
    groups: dict[str, list[Download]] = {h: [] for h in tracked}
    unknown: set[str] = set()  # the app's queue can't be read: decided by progress below
    for d in releases:
        q = in_queue(d)
        if d.real_hash in tracked or q:
            groups.setdefault(d.real_hash, []).append(d)  # type: ignore[arg-type]
        elif q is None:
            groups.setdefault(d.real_hash, []).append(d)  # type: ignore[arg-type]
            unknown.add(d.real_hash)  # type: ignore[arg-type]

    live: dict[str, dict[str, Any]] = {}
    error = None
    if groups:
        try:
            live = {
                str(t.get("hash", "")).upper(): t
                for t in await qbit.json(
                    "torrents/info", hashes="|".join(sorted(h.lower() for h in groups))
                )
            }
        except QbitError as e:
            error = str(e)

    items = []
    for real, rels in groups.items():
        q = live.get(real)
        if q is None and error is None:
            continue  # gone from qBittorrent: the status checks notice and log it
        t = tracked.get(real)
        if t is None and real in unknown and q and (q.get("progress") or 0) >= 1:
            continue  # finished, and the app's queue can't be read: assume it's been imported
        first = rels[0] if rels else None
        topic_id = t.topic_id if t else (first.topic_id if first else None)
        title = t.title if t else (first.title or first.release or first.name) if first else ""
        items.append(
            {
                "hash": real,
                "topic_id": topic_id,
                "topic_url": client.topic_url(topic_id) if topic_id else None,
                "title": title,
                "status": _status(q) if q else "unknown",
                **{k: (q.get(k) if q else None) for k in FIELDS},
                "tracked": {
                    "source": t.source,
                    "state": t.state,
                    "last_update": t.last_update.isoformat(),
                    "ttl": tracker.ttl(t),
                    "expires_at": (e.isoformat() if (e := tracker.expires_at(t)) else None),
                }
                if t
                else None,
                "releases": [
                    {
                        "release": d.release or d.name,
                        "app": "Radarr" if app_of(d.category) == "radarr" else "Sonarr",
                        "category": d.category or "",
                        "in_queue": in_queue(d),
                    }
                    for d in rels
                ],
            }
        )
    items.sort(key=lambda i: (ORDER.get(i["status"], 6), i["title"] or ""))
    totals = {
        "torrents": len(items),
        "tracked": sum(1 for i in items if i["tracked"]),
        "downloading": sum(1 for i in items if i["status"] in ("downloading", "stalled", "queued")),
        "dlspeed": sum(int(i["dlspeed"] or 0) for i in items),
        "upspeed": sum(int(i["upspeed"] or 0) for i in items),
        "size": sum(int(i["size"] or 0) for i in items),
    }
    return {"configured": True, "error": error, "items": items, "totals": totals}
