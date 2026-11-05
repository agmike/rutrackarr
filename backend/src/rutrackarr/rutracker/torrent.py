"""Just enough of a .torrent: info hash, name and file list.

The torrent itself is never stored (its announce URL carries the user's passkey); only these
fields are kept, so a download can later be matched to what qBittorrent/Sonarr report.
"""

import hashlib
from dataclasses import dataclass


class TorrentError(ValueError):
    pass


@dataclass(frozen=True)
class TorrentInfo:
    info_hash: str  # v1 SHA-1, upper-case hex (as qBittorrent/Sonarr report the download id)
    name: str
    files: list[tuple[str, int]]  # path inside the torrent ("/"-separated, without `name`), size


def read(data: bytes) -> TorrentInfo:
    root, end = _decode(data, 0)
    if end != len(data) or not isinstance(root, dict) or b"info" not in root:
        raise TorrentError("not a torrent file")
    info, (start, stop) = root[b"info"]
    if not isinstance(info, dict):
        raise TorrentError("torrent info is not a dictionary")
    info = {k: v[0] for k, v in info.items()}
    name = _text(info.get(b"name.utf-8") or info.get(b"name") or b"")
    if b"files" in info:
        files = []
        for entry, _ in info[b"files"]:
            entry = {k: v[0] for k, v in entry.items()}
            parts = entry.get(b"path.utf-8") or entry.get(b"path") or []
            files.append(("/".join(_text(p[0]) for p in parts), int(entry.get(b"length", 0))))
    else:
        files = [(name, int(info.get(b"length", 0)))]
    return TorrentInfo(hashlib.sha1(data[start:stop]).hexdigest().upper(), name, files)  # noqa: S324


def _text(b: object) -> str:
    if not isinstance(b, bytes):
        raise TorrentError("expected a byte string")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1251", errors="replace")


def _decode(data: bytes, i: int):  # type: ignore[no-untyped-def]
    """Decode one value at `i` → (value, end). Dict values and list items are (value, (start,
    end)) pairs, so the raw bytes of the info dictionary can be hashed exactly as they are."""
    try:
        c = data[i : i + 1]
        if c == b"i":
            end = data.index(b"e", i)
            return int(data[i + 1 : end]), end + 1
        if c == b"l":
            items, i = [], i + 1
            while data[i : i + 1] != b"e":
                start = i
                value, i = _decode(data, i)
                items.append((value, (start, i)))
            return items, i + 1
        if c == b"d":
            d, i = {}, i + 1
            while data[i : i + 1] != b"e":
                key, i = _decode(data, i)
                start = i
                value, i = _decode(data, i)
                d[key] = (value, (start, i))
            return d, i + 1
        if c.isdigit():
            colon = data.index(b":", i)
            n = int(data[i:colon])
            return data[colon + 1 : colon + 1 + n], colon + 1 + n
    except (ValueError, IndexError) as e:
        raise TorrentError(f"broken torrent file: {e}") from e
    raise TorrentError(f"unexpected byte at {i}")
