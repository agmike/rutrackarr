"""Torrent file lists → external tracks for Sonarr's import script."""

import hashlib

import httpx

from rutrackarr.releases.companions import find_video, plan
from rutrackarr.releases.title import parse_title
from rutrackarr.rutracker import torrent
from tests.test_rutracker_flow import api, net  # noqa: F401  (fixtures)

NIA = "[SubsPlus+] Nia Liston - The Merciless Maiden - S01E0{n} (ADN WEB-DL 1080p AVC AAC) [{crc}]"
CRC = {1: "4EFEF51F", 2: "333EA23D"}
NIA_FILES = [
    *(f"{NIA.format(n=n, crc=c)}.mkv" for n, c in CRC.items()),
    *(f"RUS Sound [StudioBand]/{NIA.format(n=n, crc=c)}.StudioBand.mka" for n, c in CRC.items()),
    *(f"RUS Subs [Amediateka]/{NIA.format(n=n, crc=c)}.Amediateka.ass" for n, c in CRC.items()),
    *(f"RUS Sound [StudioBand]/надписи/{NIA.format(n=n, crc=c)}.signs.ass" for n, c in CRC.items()),
]
NIA_TITLE = (
    "Кёран Рэйдзё Ниа Листон / Kyouran Reijou Nia Liston [TV] [1-5 из 12] [RUS(ext), JAP+Sub] "
    "[2026, WEB-DL] [1080p]"
)


def bencode(v) -> bytes:  # type: ignore[no-untyped-def]
    if isinstance(v, int):
        return b"i%de" % v
    if isinstance(v, str):
        v = v.encode()
    if isinstance(v, bytes):
        return b"%d:%s" % (len(v), v)
    if isinstance(v, list):
        return b"l" + b"".join(bencode(x) for x in v) + b"e"
    return b"d" + b"".join(bencode(k) + bencode(v[k]) for k in sorted(v)) + b"e"


def make_torrent(name: str, files: list[str]) -> tuple[bytes, str]:
    info = {
        "name": name,
        "piece length": 262144,
        "pieces": b"\0" * 20,
        "files": [{"length": 1000 + i, "path": f.split("/")} for i, f in enumerate(files)],
    }
    data = bencode({"announce": "http://bt.example/ann?uk=PASSKEY", "info": info})
    return data, hashlib.sha1(bencode(info)).hexdigest().upper()


def test_read_torrent():
    data, info_hash = make_torrent(
        "Kyouran Reijou Nia Liston [WEB-DL 1080p] [SubsPlus+]", NIA_FILES
    )
    t = torrent.read(data)
    assert t.info_hash == info_hash
    assert t.name == "Kyouran Reijou Nia Liston [WEB-DL 1080p] [SubsPlus+]"
    assert [p for p, _ in t.files] == NIA_FILES and t.files[0][1] == 1000


def test_plan_nia_liston():
    video = find_video(NIA_FILES, f"/data/download/torrent/x/{NIA.format(n=1, crc=CRC[1])}.mkv")
    assert video == f"{NIA.format(n=1, crc=CRC[1])}.mkv"
    got = {c.suffix: c.path.split("/")[0] for c in plan(NIA_FILES, video, parse_title(NIA_TITLE))}
    assert got == {
        "ru.StudioBand.mka": "RUS Sound [StudioBand]",
        "ru.Amediateka.ass": "RUS Subs [Amediateka]",
        "ru.StudioBand signs.forced.ass": "RUS Sound [StudioBand]",
    }


def test_plan_language_from_title_and_folders():
    files = [
        "Film.mkv",
        "Озвучка/Film.Gavrilov.ac3",
        "Subs/Film.srt",
        "Subs ENG/Film.srt",
        "Sample/sample.mkv",
    ]
    t = parse_title("Ф / F (Р / D) [1999, США, BDRip] Dub + Original Eng + Sub (Rus, Eng)")
    got = {c.path: c.suffix for c in plan(files, "Film.mkv", t)}
    # Two videos (sample), so only name-matched tracks. The title's only non-original audio is
    # the Russian dub, so the audio is Russian; English subtitles from the folder; the other
    # subtitle's language is ambiguous for this title (Rus and Eng), so none is guessed.
    assert got == {
        "Озвучка/Film.Gavrilov.ac3": "ru.Gavrilov.ac3",
        "Subs ENG/Film.srt": "en.srt",
        "Subs/Film.srt": "srt",
    }


def test_single_film_takes_all_tracks_and_numbers_duplicates():
    files = ["Movie (1999).mkv", "RUS/dub.ac3", "RUS/mvo.ac3", "Subs/rus.srt", "Subs/rus2.srt"]
    got = {c.path: c.suffix for c in plan(files, "Movie (1999).mkv")}
    assert got == {
        "RUS/dub.ac3": "ru.ac3",
        "RUS/mvo.ac3": "ru.2.ac3",
        "Subs/rus.srt": "ru.srt",
        "Subs/rus2.srt": "ru.rus2.srt",
    }


def key(api) -> str:  # noqa: F811
    return api.get("/api/settings/api-key").json()["api_key"]


def test_download_then_companions(api, net):  # noqa: F811
    data, info_hash = make_torrent(
        "Kyouran Reijou Nia Liston [WEB-DL 1080p] [SubsPlus+]", NIA_FILES
    )
    net.on(
        "GET",
        "/forum/dl.php",
        httpx.Response(200, content=data, headers={"content-type": "application/x-bittorrent"}),
    )
    k = key(api)
    assert api.get("/torznab/download/6830000", params={"apikey": k}).content == data
    src = f"/data/download/torrent/Kyouran Reijou Nia Liston [WEB-DL 1080p] [SubsPlus+]/{NIA.format(n=2, crc=CRC[2])}.mkv"
    r = api.get(
        "/torznab/companions", params={"hash": info_hash.lower(), "source": src, "apikey": k}
    )
    assert r.status_code == 200, r.text
    lines = [line.split("\t") for line in r.text.splitlines()]
    assert lines[0] == ["#video", f"{NIA.format(n=2, crc=CRC[2])}.mkv"]
    assert sorted(s for _, s in lines[1:]) == [
        "ru.Amediateka.ass",
        "ru.StudioBand signs.forced.ass",
        "ru.StudioBand.mka",
    ]
    assert all("S01E02" in p for p, _ in lines[1:])
    assert (
        api.get(
            "/torznab/companions", params={"hash": "0" * 40, "source": src, "apikey": k}
        ).status_code
        == 404
    )
    assert (
        api.get("/torznab/companions", params={"hash": info_hash, "source": src}).status_code == 401
    )
