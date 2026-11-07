"""A qBittorrent Web API in front of the real qBittorrent, for Sonarr/Radarr.

Everything is passed through, except what makes RuTracker topics import like any other release:

- ``torrents/add`` of a torrent RuTrackarr served marked (its release name in the info dict, so
  each release has its own hash): the mark is stripped and the real torrent — the topic as
  RuTracker serves it — is added stopped, its video files renamed with the release's language
  tokens ("… OrigAudio RusSubs RTA-T1 -RuTracker.mkv", so the imported file scores like the
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

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Request, Response
from starlette.datastructures import UploadFile

from rutrackarr.qbit.upstream import Qbit, QbitError
from rutrackarr.releases.naming import file_tag, tagged
from rutrackarr.rutracker import torrent
from rutrackarr.torznab.downloads import Download, DownloadStore

log = logging.getLogger(__name__)
router = APIRouter()

COOKIE = "SID"
FINISHED_STOPPED = {"pausedUP", "stoppedUP"}
ADD_WAIT_SECONDS = 15


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
    proxy = _Proxy(qbit, request.app.state.downloads)
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
    def __init__(self, qbit: Qbit, store: DownloadStore) -> None:
        self.qbit, self.store = qbit, store
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
            add = {k: v for k, v in fields.items() if k not in ("stopped", "paused", "urls")}
            add |= {"stopped": "true", "paused": "true"}
            r = await self.qbit.request(
                "POST", "torrents/add", data=add,
                files=[("torrents", (filename, real, "application/x-bittorrent"))],
            )  # fmt: skip
            if r.status_code != 200 or r.text.strip() == "Fails.":
                log.warning("qbit add %s failed: HTTP %s %s", rhash, r.status_code, r.text[:200])
                return False
            await self._rename(rhash, file_tag(release))
            if not want_stopped:
                await self._start(rhash)
        elif category and present[0].get("category") != category:
            # In use again (a new release of a finished topic): back to the download category.
            await self._move(rhash, category)
        self.store.added(virtual_info, release, rhash, category)
        log.info("qbit add: %s → %s (%s)", release, rhash, "new" if not present else "present")
        return True

    async def _files(self, rhash: str) -> list[dict[str, Any]]:
        for _ in range(ADD_WAIT_SECONDS * 4):
            r = await self.qbit.request("GET", "torrents/files", params={"hash": rhash})
            if r.status_code == 200 and (files := r.json()):
                return files  # type: ignore[no-any-return]
            await asyncio.sleep(0.25)
        raise QbitError(f"torrent {rhash} did not show up in qBittorrent")

    async def _rename(self, rhash: str, tag: str) -> None:
        for f in await self._files(rhash):
            old = f.get("name", "")
            new = tagged(old, tag)
            if new != old:
                r = await self.qbit.post(
                    "torrents/renameFile", hash=rhash, oldPath=old, newPath=new
                )
                if r.status_code != 200:
                    log.warning("qbit rename %s: HTTP %s", old, r.status_code)

    async def _move(self, rhash: str, category: str) -> None:
        r = await self.qbit.post("torrents/setCategory", hashes=rhash, category=category)
        if r.status_code != 200:
            log.warning("qbit move %s to %r: HTTP %s", rhash, category, r.status_code)

    async def _start(self, rhash: str) -> None:
        r = await self.qbit.post("torrents/start", hashes=rhash)
        if r.status_code == 404:  # qBittorrent < 5
            await self.qbit.post("torrents/resume", hashes=rhash)

    # --- torrents/info -----------------------------------------------------------------------

    async def info(self, params: dict[str, str]) -> Response:
        active = self.active()
        by_hash = {d.info_hash: d for d in active}
        managed = {d.real_hash for d in active}
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
            for d in wanted:
                if (real := reals.get(d.real_hash or "")) is not None:
                    out.append(_virtual(real, d))
        return Response(_json(out), media_type="application/json")

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
            if cats == {category} and category:
                await self._move(real.lower(), category)
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
        reals = {virtual[h].real_hash for h in removed} - still_used
        rest = [h for h in hashes if h and h.upper() not in virtual]
        rest += [h.lower() for h in reals if h]
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
        if path == "torrents/properties" and r.status_code == 200 and asked:
            props = r.json()
            if isinstance(props, dict) and "hash" in props:
                props["hash"] = asked.lower()
            content = _json(props)
        return Response(
            content, status_code=r.status_code, media_type=r.headers.get("content-type")
        )


def _virtual(real: dict[str, Any], d: Download) -> dict[str, Any]:
    t = dict(real)
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
