"""Adding a RuTracker topic's torrent to qBittorrent the RuTrackarr way: stopped, its video
files renamed with the release's language tag, then started. Shared by the download client proxy
(Sonarr/Radarr grabs) and tracked topics (added by hand)."""

import asyncio
import logging
from typing import Any

from rutrackarr.qbit.upstream import Qbit, QbitError
from rutrackarr.releases.naming import tagged

log = logging.getLogger(__name__)
ADD_WAIT_SECONDS = 15


async def present(qbit: Qbit, rhash: str) -> dict[str, Any] | None:
    """The torrent as qBittorrent lists it, or None."""
    found = await qbit.json("torrents/info", hashes=rhash.lower())
    return found[0] if found else None


async def add(
    qbit: Qbit,
    data: bytes,
    filename: str,
    tag: str,
    fields: dict[str, str],
    stopped: bool = False,
) -> bool:
    """Add the torrent (`fields`: qBittorrent's add form — category, savepath…), rename, start."""
    from rutrackarr.rutracker import torrent

    rhash = torrent.read(data).info_hash.lower()
    form = {k: v for k, v in fields.items() if k not in ("stopped", "paused", "urls")}
    form |= {"stopped": "true", "paused": "true"}
    r = await qbit.request(
        "POST", "torrents/add", data=form,
        files=[("torrents", (filename, data, "application/x-bittorrent"))],
    )  # fmt: skip
    if r.status_code != 200 or r.text.strip() == "Fails.":
        log.warning("qbit add %s failed: HTTP %s %s", rhash, r.status_code, r.text[:200])
        return False
    await rename(qbit, rhash, tag)
    if not stopped:
        await start(qbit, rhash)
    return True


async def files(qbit: Qbit, rhash: str) -> list[dict[str, Any]]:
    for _ in range(ADD_WAIT_SECONDS * 4):
        r = await qbit.request("GET", "torrents/files", params={"hash": rhash})
        if r.status_code == 200 and (found := r.json()):
            return found  # type: ignore[no-any-return]
        await asyncio.sleep(0.25)
    raise QbitError(f"torrent {rhash} did not show up in qBittorrent")


async def rename(qbit: Qbit, rhash: str, tag: str) -> None:
    for f in await files(qbit, rhash):
        old = f.get("name", "")
        new = tagged(old, tag)
        if new != old:
            r = await qbit.post("torrents/renameFile", hash=rhash, oldPath=old, newPath=new)
            if r.status_code != 200:
                log.warning("qbit rename %s: HTTP %s", old, r.status_code)


async def move(qbit: Qbit, rhash: str, category: str) -> None:
    r = await qbit.post("torrents/setCategory", hashes=rhash, category=category)
    if r.status_code != 200:
        log.warning("qbit move %s to %r: HTTP %s", rhash, category, r.status_code)


async def start(qbit: Qbit, rhash: str) -> None:
    r = await qbit.post("torrents/start", hashes=rhash)
    if r.status_code == 404:  # qBittorrent < 5
        await qbit.post("torrents/resume", hashes=rhash)


async def delete(qbit: Qbit, rhash: str, delete_files: bool) -> None:
    await qbit.post(
        "torrents/delete", hashes=rhash, deleteFiles="true" if delete_files else "false"
    )
