"""Which file of a topic is episode N.

RuTracker packs name their files any way their releaser likes: "Show.S02E07.1080p…",
"[Group] Show - 07 (1080p) [ABCD1234]", "07. Title.mkv", "Show [07].mkv"… Tried in order:
1. an explicit SxxEyy / Exx / EPxx in every file name;
2. the number that varies from file to file (the episode), ignoring resolutions, codecs, hashes;
3. the files in natural order, when their count is the topic's episode range.
Extras (NCOP/NCED, trailers, menus, "Specials"/"Extras" folders) are set aside first.
"""

import re
from pathlib import PurePosixPath

from rutrackarr.releases.naming import VIDEO_EXTS

_EXTRA_DIRS = re.compile(r"(?i)\b(extras?|bonus|specials?|sp|ova|ncop|nced|menus?|trailers?|pv)\b")
_EXTRA_NAMES = re.compile(
    r"(?i)\b(nc ?op|nc ?ed|creditless|trailer|teaser|preview|pv\d*|menu|cm\d*)\b"
)
_EXPLICIT = re.compile(r"(?i)(?:\bS\d{1,2}[ ._-]?E|\bEP?\.?\s?)(\d{1,4})(?!\d)")
_NUMBER = re.compile(r"(?<![0-9A-Za-z])(\d{1,4})(?:v\d)?(?![0-9A-Za-z])")
_NOISE = re.compile(r"\[[0-9A-Fa-f]{8}\]|\(\d{4}\)|\b(?:19|20)\d{2}\b")  # CRC hashes, years


def _natural(s: str) -> list:  # type: ignore[type-arg]
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


def videos(files: list[str]) -> list[str]:
    """The episode files: videos, extras set aside (unless that leaves none)."""
    vids = [f for f in files if PurePosixPath(f).suffix.lower() in VIDEO_EXTS]
    main = [
        f
        for f in vids
        if not any(_EXTRA_DIRS.search(part) for part in PurePosixPath(f).parent.parts)
        and not _EXTRA_NAMES.search(PurePosixPath(f).stem)
    ]
    return main or vids


def episode_numbers(
    files: list[str], first: int | None = None, last: int | None = None
) -> dict[int, str]:
    """Episode number → file, for the episode files of a topic ({} when it can't tell)."""
    eps = sorted(videos(files), key=_natural)
    if not eps:
        return {}
    stems = [PurePosixPath(f).stem for f in eps]
    explicit = [_EXPLICIT.findall(s) for s in stems]
    if all(explicit):
        nums = [int(m[-1]) for m in explicit]
        if len(set(nums)) == len(nums):
            return dict(zip(nums, eps, strict=True))
    numbers = [[int(n) for n in _NUMBER.findall(_NOISE.sub(" ", s))] for s in stems]
    width = min(len(n) for n in numbers)
    for k in range(width):
        column = [n[k] for n in numbers]
        if len(set(column)) != len(column) or len(column) == 1:
            continue
        if first is not None and last is not None and not all(first <= c <= last for c in column):
            continue
        return dict(zip(column, eps, strict=True))
    if first is not None and last is not None and len(eps) == last - first + 1:
        return {first + i: f for i, f in enumerate(eps)}
    if len(eps) == 1 and first is not None and first == last:
        return {first: eps[0]}
    return {}


_SEASON_EPISODE = re.compile(r"(?i)\bS\d{1,2}[ ._-]?E\d{1,4}")


def season_marks(
    files: list[str], season: int | None, first: int | None = None, last: int | None = None
) -> dict[str, str]:
    """Video file → "S02E01" for a topic of season 2 or later whose files number its episodes
    from 1 without saying the season ("Show II - 01.mkv"): Sonarr would read the bare number as
    an absolute episode (→ S01E01) and refuse the import. {} when the files already say
    "SxxEyy", the numbers don't start at 1 (absolute numbering: Sonarr maps those itself), or
    which file is which episode can't be told."""
    if season is None or season < 2:
        return {}
    vids = videos(files)
    if not vids or any(_SEASON_EPISODE.search(PurePosixPath(f).stem) for f in vids):
        return {}
    numbers = episode_numbers(files, first, last)
    if not numbers or min(numbers) != 1:
        return {}
    return {f: f"S{season:02d}E{n:02d}" for n, f in numbers.items()}


def episode_file(
    files: list[str], n: int, first: int | None = None, last: int | None = None
) -> str | None:
    return episode_numbers(files, first, last).get(n)
