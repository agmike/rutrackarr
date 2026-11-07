"""A qBittorrent Web API in front of the real qBittorrent, for Sonarr/Radarr.

Everything is passed through, except what makes RuTracker topics import like any other release:

- ``torrents/add`` of a torrent RuTrackarr served marked (its release name in the info dict, so
  each release has its own hash): the mark is stripped and the real torrent — the topic as
  RuTracker serves it — is added stopped, its video files renamed with the release's language
  tokens ("… OrigAudio RusSoftSubs RTA-T1 -RuTracker.mkv", so the imported file scores like the
  grab), then started unless Sonarr/Radarr asked for it stopped. A topic already in qBittorrent
  is reused.
- The release is a *virtual* download: Sonarr/Radarr see it under its own hash, with the release
  name as its name and their category, backed by the real torrent (progress, state, paths). The
  real torrent itself is hidden from them. A finished virtual download is reported seeding, so
  files are hardlinked/copied, never moved out of the shared topic.
- Commands on a virtual hash go to the real torrent; ``setCategory`` only changes the virtual
  download; ``delete`` removes it, and the real torrent too once no release uses it.

Sonarr and Radarr log in with the RuTrackarr API key as the password (any user name).
"""

import hashlib
import hmac
import json
import logging
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, Request, Response
from starlette.datastructures import UploadFile

from rutrackarr.activity import Activity
from rutrackarr.qbit import topics
from rutrackarr.qbit.upstream import Qbit, QbitError
from rutrackarr.releases.companions import FONTS, plan
from rutrackarr.releases.episodes import episode_file
from rutrackarr.releases.naming import file_tag, untagged
from rutrackarr.releases.title import parse_title
from rutrackarr.rutracker import torrent
from rutrackarr.torznab.downloads import Download, DownloadStore

log = logging.getLogger(__name__)
router = APIRouter()

COOKIE = "SID"
FINISHED_STOPPED = {"pausedUP", "stoppedUP"}


def _token(api_key: str) -> str:
    return hmac.new(api_key.encode(), b"rutrackarr-qbit-session", hashlib.sha256).hexdigest()


def _authorized(request: Request) -> bool:
    key = request.app.state.settings_service.api_key()
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].strip(), key):
        return True
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), _token(key))


def _text(body: str, status: int = 200) -> Response:
    return Response(body, status_code=status, media_type="text/plain; charset=UTF-8")


@router.api_route("/api/v2/{path:path}", methods=["GET", "POST"], include_in_schema=False)
async def api(path: str, request: Request) -> Response:
    if path == "auth/login":
        return await _login(request)
    if path == "auth/logout":
        return _text("Ok.")
    if not _authorized(request):
        return _text("Forbidden", 403)
    qbit: Qbit = request.app.state.qbit
    if not qbit.configured():
        return _text("RuTrackarr: qBittorrent is not configured", 502)
    await request.body()  # cached: forwarded as is, and parsed as a form where needed
    proxy = _Proxy(
        qbit, request.app.state.downloads, request.app.state.activity, request.app.state.tracker,
        request.app.state.settings_service.get,
    )  # fmt: skip
    try:
        if path == "torrents/add" and request.method == "POST":
            return await proxy.add(request)
        params = await _params(request)
        if path == "torrents/info":
            return await proxy.info(params)
        virtual = proxy.virtual_hashes()
        hashes = [h for h in params.get("hashes", "").split("|") if h]
        if path == "torrents/setCategory" and any(h.upper() in virtual for h in hashes):
            return await proxy.set_category(params, virtual)
        if path == "torrents/delete" and any(h.upper() in virtual for h in hashes):
            return await proxy.delete(params, virtual)
        if params.get("hash", "").upper() in virtual or any(h.upper() in virtual for h in hashes):
            return await proxy.mapped(request.method, path, params, virtual)
        return await proxy.forward(request, path)
    except QbitError as e:
        log.warning("qbit proxy %s: %s", path, e)
        return _text(str(e), 502)


async def _login(request: Request) -> Response:
    form = await request.form()
    key = request.app.state.settings_service.api_key()
    if not hmac.compare_digest(str(form.get("password", "")), key):
        return _text("Fails.")
    r = _text("Ok.")
    r.set_cookie(COOKIE, _token(key), httponly=True, samesite="strict")
    return r


async def _params(request: Request) -> dict[str, str]:
    params = dict(request.query_params)
    if request.method == "POST":
        form = await request.form()
        params |= {k: v for k, v in form.items() if isinstance(v, str)}
    return params


class _Proxy:
    def __init__(
        self, qbit: Qbit, store: DownloadStore, activity: Activity, tracker: Any, settings: Any
    ) -> None:
        self.qbit, self.store, self.activity, self.tracker = qbit, store, activity, tracker
        self.settings = settings
        self._active: list[Download] | None = None

    def active(self) -> list[Download]:
        if self._active is None:
            self._active = [d for d in self.store.active() if d.real_hash]
        return self._active

    def virtual_hashes(self) -> dict[str, Download]:
        return {d.info_hash: d for d in self.active()}

    async def forward(self, request: Request, path: str) -> Response:
        headers = {
            k: v for k, v in request.headers.items() if k.lower() in ("content-type", "accept")
        }
        r = await self.qbit.request(
            request.method, path, params=request.query_params, content=await request.body(),
            headers=headers,
        )  # fmt: skip
        return Response(
            r.content, status_code=r.status_code, media_type=r.headers.get("content-type")
        )

    # --- torrents/add ------------------------------------------------------------------------

    async def add(self, request: Request) -> Response:
        form = await request.form()
        fields = {k: v for k, v in form.items() if isinstance(v, str)}
        marked: list[tuple[str, bytes]] = []
        plain: list[tuple[str, bytes]] = []
        for upload in form.getlist("torrents"):
            if not isinstance(upload, UploadFile):
                continue
            data = await upload.read()
            try:
                _, release = torrent.unmark(data)
            except torrent.TorrentError:
                release = None
            (marked if release else plain).append((upload.filename or "torrent", data))
        if not marked:
            r = await self.qbit.request(
                "POST", "torrents/add", data=fields,
                files=[("torrents", (n, d, "application/x-bittorrent")) for n, d in plain],
            )  # fmt: skip
            return Response(r.content, status_code=r.status_code, media_type="text/plain")
        for name, data in marked:
            if not await self._add_marked(name, data, fields):
                return _text("Fails.")
        if plain or fields.get("urls"):
            r = await self.qbit.request(
                "POST", "torrents/add", data=fields,
                files=[("torrents", (n, d, "application/x-bittorrent")) for n, d in plain] or None,
            )  # fmt: skip
            if r.text.strip() == "Fails.":
                return _text("Fails.")
        return _text("Ok.")

    async def _add_marked(self, filename: str, data: bytes, fields: dict[str, str]) -> bool:
        real, release = torrent.unmark(data)
        assert release is not None
        virtual_info, real_info = torrent.read(data), torrent.read(real)
        rhash = real_info.info_hash.lower()
        category = fields.get("category", "")
        want_stopped = "true" in (
            fields.get("stopped", "").lower(),
            fields.get("paused", "").lower(),
        )
        present = await self.qbit.json("torrents/info", hashes=rhash)
        if not present:
            if not await topics.add(
                self.qbit, real, filename, file_tag(release), fields, stopped=want_stopped
            ):
                return False
        elif (
            category
            and present[0].get("category") != category
            and not self.tracker.owns(rhash)  # a topic tracked by hand stays where it is
        ):
            # In use again (a new release of a finished topic): back to the download category.
            await self._move(rhash, category)
        self.store.added(virtual_info, release, rhash, category)
        if (grabbed := self.store.get(virtual_info.info_hash)) is not None:
            self.tracker.on_grab(grabbed, rhash)
            await self._files_for(grabbed, rhash, fresh=not present)
        how = "files tagged, started" if not want_stopped else "files tagged, stopped"
        self.activity.event(
            "added",
            f"Added to qBittorrent ({category or 'no category'}): {release} — "
            + (how if not present else "its topic was already there"),
        )
        log.info("qbit add: %s → %s (%s)", release, rhash, "new" if not present else "present")
        return True

    async def _files_for(self, d: Download, rhash: str, fresh: bool) -> None:
        """A single-episode release: find its video file in the topic. With "download only the
        grabbed episodes" on, a topic added for it gets only that episode (and its tracks);
        later grabs from the topic switch theirs on."""
        files = await topics.files(self.qbit, rhash)
        names = [untagged(str(f.get("name", ""))) for f in files]
        only = str(self.settings("download.only_grabbed") or "off") == "on"
        if d.episode is None:
            if only and any(f.get("priority") == 0 for f in files):
                await _want(self.qbit, rhash, [int(f["index"]) for f in files])  # whole topic
            return
        e = parse_title(d.title).episodes if d.title else None
        video = episode_file(names, d.episode, e.first if e else None, e.last if e else None)
        self.store.set_file(d.info_hash, video)
        if video is None:
            self.activity.event(
                "episode_unknown",
                f"Couldn't tell which file of the topic is episode {d.episode}: "
                f"{d.release} downloads as the whole topic",
                level="warn", topic_id=d.topic_id or None,
            )  # fmt: skip
            return
        if not only:
            return
        wanted = (
            {video}
            | {c.path for c in plan(names, video)}
            | {n for n in names if PurePosixPath(n).suffix.lower() in FONTS}
        )
        indices = [int(f["index"]) for f, n in zip(files, names, strict=True) if n in wanted]
        if fresh:
            others = [int(f["index"]) for f, n in zip(files, names, strict=True) if n not in wanted]
            if others:
                await self.qbit.post(
                    "torrents/filePrio", hash=rhash, id="|".join(map(str, others)), priority="0"
                )
        await _want(self.qbit, rhash, indices)

    async def _move(self, rhash: str, category: str) -> None:
        await topics.move(self.qbit, rhash, category)

    # --- torrents/info -----------------------------------------------------------------------

    async def info(self, params: dict[str, str]) -> Response:
        active = self.active()
        by_hash = {d.info_hash: d for d in active}
        managed = {d.real_hash for d in active} | {t.info_hash for t in self.tracker.all(False)}
        asked = [h for h in params.get("hashes", "").split("|") if h]
        virtual_asked = [by_hash[h.upper()] for h in asked if h.upper() in by_hash]
        upstream = dict(params)
        out: list[dict[str, Any]] = []
        if asked:
            rest = [h for h in asked if h.upper() not in by_hash]
            upstream["hashes"] = "|".join(rest)
            wanted = virtual_asked
        else:
            wanted = active
        if not asked or upstream["hashes"]:
            out = [t for t in await self.qbit.json("torrents/info", **upstream)]
            out = [t for t in out if str(t.get("hash", "")).upper() not in managed]
        if "category" in params:
            wanted = [d for d in wanted if (d.category or "") == params["category"]]
        if wanted:
            hashes = "|".join(sorted({d.real_hash.lower() for d in wanted if d.real_hash}))
            reals = {
                str(t.get("hash", "")).upper(): t
                for t in await self.qbit.json("torrents/info", hashes=hashes)
            }
            files = await self._files_of({d.real_hash for d in wanted if d.file and d.real_hash})
            for d in wanted:
                if (real := reals.get(d.real_hash or "")) is not None:
                    out.append(_virtual(real, d, _file(files, d)))
                else:
                    forget_gone(self.store, self.activity, d, self.tracker)
        return Response(_json(out), media_type="application/json")

    async def _files_of(self, reals: set[str | None]) -> dict[str, list[dict[str, Any]]]:
        out = {}
        for real in sorted(r for r in reals if r):
            r = await self.qbit.request("GET", "torrents/files", params={"hash": real.lower()})
            out[real] = r.json() if r.status_code == 200 else []
        return out

    # --- commands on virtual hashes ----------------------------------------------------------

    async def set_category(self, params: dict[str, str], virtual: dict[str, Download]) -> Response:
        hashes = params.get("hashes", "").split("|")
        category = params.get("category", "")
        for h in hashes:
            if h.upper() in virtual:
                self.store.set_category(h, category)
        # A topic follows its releases (e.g. to the post-import category) once all of them
        # are in the same category; while one is still elsewhere, the topic stays put.
        reals = {virtual[h.upper()].real_hash for h in hashes if h.upper() in virtual}
        active = [d for d in self.store.active() if d.real_hash]
        for real in sorted(r for r in reals if r):
            cats = {d.category or "" for d in active if d.real_hash == real}
            if cats == {category} and category and not self.tracker.owns(real):
                await self._move(real.lower(), category)
                names = [d.release or d.name for d in active if d.real_hash == real]
                self.activity.event(
                    "moved", f"Moved to {category}: {'; '.join(names)} (topic torrent followed)"
                )
        rest = [h for h in hashes if h and h.upper() not in virtual]
        if rest:
            r = await self.qbit.post(
                "torrents/setCategory", hashes="|".join(rest), category=category
            )
            return Response(r.content, status_code=r.status_code)
        return _text("")

    async def delete(self, params: dict[str, str], virtual: dict[str, Download]) -> Response:
        hashes = params.get("hashes", "").split("|")
        delete_files = params.get("deleteFiles", "false")
        removed = {h.upper() for h in hashes if h.upper() in virtual}
        for h in removed:
            self.store.removed(h)
        still_used = {d.real_hash for d in self.active() if d.info_hash not in removed}
        # A topic tracked by hand stays: RuTrackarr's, not Sonarr's/Radarr's to delete.
        reals = {
            r for r in {virtual[h].real_hash for h in removed} - still_used
            if r and not self.tracker.owns(r)
        }  # fmt: skip
        rest = [h for h in hashes if h and h.upper() not in virtual]
        rest += [h.lower() for h in reals if h]
        for h in removed:
            d = virtual[h]
            gone = d.real_hash in reals
            self.activity.event(
                "removed",
                f"Removed by the download client: {d.release or d.name}"
                + (
                    f" — topic torrent deleted{' with its files' if delete_files == 'true' else ''}"
                    if gone
                    else " — topic torrent kept (other releases use it)"
                ),
            )
        if rest:
            r = await self.qbit.post(
                "torrents/delete", hashes="|".join(rest), deleteFiles=delete_files
            )
            return Response(r.content, status_code=r.status_code)
        return _text("")

    async def mapped(
        self, method: str, path: str, params: dict[str, str], virtual: dict[str, Download]
    ) -> Response:
        """Any other call naming virtual hashes: sent to the real torrents."""

        def real(h: str) -> str:
            d = virtual.get(h.upper())
            return (d.real_hash or h).lower() if d else h

        out = dict(params)
        if "hash" in out:
            out["hash"] = real(out["hash"])
        if "hashes" in out:
            out["hashes"] = "|".join(dict.fromkeys(real(h) for h in out["hashes"].split("|")))
        if method == "GET":
            r = await self.qbit.request("GET", path, params=out)
        else:
            r = await self.qbit.request("POST", path, data=out)
        content = r.content
        asked = params.get("hash", "")
        single = virtual.get(asked.upper())
        if path == "torrents/files" and r.status_code == 200 and single and single.file:
            content = _json(
                [f for f in r.json() if untagged(str(f.get("name", ""))) == single.file]
            )
        if path == "torrents/properties" and r.status_code == 200 and asked:
            props = r.json()
            if isinstance(props, dict) and "hash" in props:
                props["hash"] = asked.lower()
            content = _json(props)
        return Response(
            content, status_code=r.status_code, media_type=r.headers.get("content-type")
        )


def _file(files: dict[str, list[dict[str, Any]]], d: Download) -> dict[str, Any] | None:
    """A single-episode release's video file in its topic's file list (live: name, size,
    progress)."""
    if not d.file or not d.real_hash:
        return None
    return next(
        (f for f in files.get(d.real_hash, []) if untagged(str(f.get("name", ""))) == d.file), None
    )


def _virtual(
    real: dict[str, Any], d: Download, file: dict[str, Any] | None = None
) -> dict[str, Any]:
    t = dict(real)
    if file is not None:
        # Just the episode: its file is the content, its progress the download's.
        size, progress = int(file.get("size") or 0), float(file.get("progress") or 0)
        t["content_path"] = f"{str(real.get('save_path', '')).rstrip('/')}/{file.get('name', '')}"
        t["size"], t["total_size"], t["progress"] = size, size, progress
        t["amount_left"] = round(size * (1 - progress))
        t["completed"] = size - t["amount_left"]
        if progress >= 1:
            t["state"], t["eta"] = "stalledUP", 0
    t["hash"] = d.info_hash.lower()
    if "infohash_v1" in t:
        t["infohash_v1"] = d.info_hash.lower()
    t["name"] = d.release or t.get("name", "")
    t["category"] = d.category or ""
    if t.get("state") in FINISHED_STOPPED:
        t["state"] = "stalledUP"  # never "done seeding": files stay where the topic seeds
    return t


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


def forget_gone(store: DownloadStore, activity: Activity, d: Download, tracker: Any = None) -> None:
    """A release whose topic torrent is no longer in qBittorrent: stop tracking it."""
    store.removed(d.info_hash)
    if tracker is not None and d.real_hash:
        tracker.gone(d.real_hash)
    activity.event(
        "gone",
        f"Topic torrent removed from qBittorrent: {d.release or d.name} — no longer tracked",
        level="warn",
        topic_id=d.topic_id or None,
    )


async def _want(qbit: Qbit, rhash: str, indices: list[int]) -> None:
    if indices:
        await qbit.post(
            "torrents/filePrio", hash=rhash, id="|".join(map(str, indices)), priority="1"
        )
