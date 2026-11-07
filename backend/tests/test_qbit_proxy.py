"""qBittorrent proxy: marked torrents → real topic added stopped, renamed, started; virtual
downloads in Sonarr's view; commands mapped to the real torrent."""

import email
import json
from urllib.parse import parse_qs

import httpx
import pytest

from rutrackarr.releases.naming import file_tag, tagged
from rutrackarr.rutracker import torrent
from tests.test_companions import CRC, NIA, NIA_FILES, make_torrent
from tests.test_rutracker_flow import api, net  # noqa: F401  (fixtures)

TOPIC = "Kyouran Reijou Nia Liston [WEB-DL 1080p] [SubsPlus+]"
RELEASE = (
    "Kyouran Reijou Nia Liston S01 1080p WEB-DL JAPANESE RUSSIAN "
    "OrigAudio OrigSoftSubs RusVoice RusSoftSubs RTA-T1 -RuTracker"
)
CATEGORY = "sonarr-rutracker"


class FakeQbit:
    """Just enough qBittorrent: torrents by hash, files, rename, start, delete, categories."""

    def __init__(self) -> None:
        self.torrents: dict[str, dict] = {}
        self.files: dict[str, list[str]] = {}
        self.added: list[dict] = []
        self.calls: list[str] = []
        self.modern_login = True  # qBittorrent 5.2+: 204 on success

    def install(self, net) -> None:  # noqa: F811
        for path in (
            "auth/login", "app/webapiVersion", "torrents/info", "torrents/add", "torrents/files",
            "torrents/renameFile", "torrents/start", "torrents/delete", "torrents/properties",
            "torrents/setCategory", "torrents/topPrio",
        ):  # fmt: skip
            for method in ("GET", "POST"):
                net.on(method, f"/api/v2/{path}", self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v2/")
        self.calls.append(path)
        if path == "auth/login":
            r = httpx.Response(204) if self.modern_login else httpx.Response(200, text="Ok.")
            r.headers["set-cookie"] = "SID=upstream; HttpOnly; path=/"
            return r
        if "SID=upstream" not in request.headers.get("cookie", ""):
            return httpx.Response(403, text="Forbidden")
        if path == "torrents/add":
            return self.add(request)
        p = {k: v[0] for k, v in parse_qs(request.url.query.decode()).items()}
        if request.method == "POST":
            p |= {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if path == "app/webapiVersion":
            return httpx.Response(200, text="2.11.4")
        if path == "torrents/info":
            out = list(self.torrents.values())
            if "hashes" in p:
                out = [t for t in out if t["hash"] in p["hashes"].split("|")]
            if "category" in p:
                out = [t for t in out if t["category"] == p["category"]]
            return httpx.Response(200, json=out)
        h = p.get("hash", "")
        if path == "torrents/files":
            if h not in self.files:
                return httpx.Response(404, text="Not Found")
            return httpx.Response(
                200, json=[{"index": i, "name": n} for i, n in enumerate(self.files[h])]
            )
        if path == "torrents/properties":
            if h not in self.torrents:
                return httpx.Response(404, text="Not Found")
            return httpx.Response(
                200, json={"hash": h, "save_path": "/data/torrents/sonarr", "seeding_time": 5}
            )
        if path == "torrents/renameFile":
            files = self.files[h]
            files[files.index(p["oldPath"])] = p["newPath"]
            return httpx.Response(200)
        hashes = p.get("hashes", "").split("|")
        if path == "torrents/start":
            for x in hashes:
                self.torrents[x]["state"] = "downloading"
            return httpx.Response(200)
        if path == "torrents/delete":
            for x in hashes:
                self.torrents.pop(x, None)
            self.calls.append(f"delete:{p['hashes']}:{p.get('deleteFiles')}")
            return httpx.Response(200)
        if path == "torrents/setCategory":
            for x in hashes:
                self.torrents[x]["category"] = p["category"]
            return httpx.Response(200)
        return httpx.Response(200)

    def add(self, request: httpx.Request) -> httpx.Response:
        head = f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
        msg = email.message_from_bytes(head + request.content)
        fields, uploads = {}, []
        for part in msg.get_payload():
            name = part.get_param("name", header="content-disposition")
            if name == "torrents":
                uploads.append(part.get_payload(decode=True))
            else:
                fields[name] = part.get_payload(decode=True).decode()
        for data in uploads:
            info = torrent.read(data)
            h = info.info_hash.lower()
            self.added.append({"hash": h, "fields": fields, "data": data})
            self.files[h] = [f"{info.name}/{p}" for p, _ in info.files]
            stopped = "true" in (fields.get("stopped"), fields.get("paused"))
            self.torrents[h] = {
                "hash": h, "infohash_v1": h, "name": info.name,
                "category": fields.get("category", ""), "progress": 0.0, "size": 1,
                "state": "stoppedDL" if stopped else "downloading",
                "save_path": "/data/torrents/sonarr",
                "content_path": f"/data/torrents/sonarr/{info.name}",
            }  # fmt: skip
        return httpx.Response(200, text="Ok.")


@pytest.fixture
def qbit(api, net):  # noqa: F811
    fake = FakeQbit()
    fake.install(net)
    r = api.put(
        "/api/settings",
        json={"values": {"qbittorrent.url": "http://gluetun:8090", "qbittorrent.password": "pw"}},
    )
    assert r.status_code == 200, r.text
    return fake


def key(api) -> str:  # noqa: F811
    return api.get("/api/settings/api-key").json()["api_key"]


def serve(api, net, name: str = RELEASE) -> tuple[bytes, bytes]:  # noqa: F811
    data, _ = make_torrent(TOPIC, NIA_FILES)
    net.on("GET", "/forum/dl.php", httpx.Response(200, content=data))
    r = api.get("/torznab/download/6830000", params={"apikey": key(api), "name": name})
    assert r.status_code == 200
    return data, r.content


def login(api) -> None:  # noqa: F811
    assert (
        api.post("/qbit/api/v2/auth/login", data={"username": "x", "password": "no"}).text
        == "Fails."
    )
    r = api.post("/qbit/api/v2/auth/login", data={"username": "sonarr", "password": key(api)})
    assert r.text == "Ok." and "SID" in r.cookies


def add(api, marked: bytes, **fields: str) -> httpx.Response:  # noqa: F811
    return api.post(
        "/qbit/api/v2/torrents/add",
        data={"category": CATEGORY, **fields},
        files={"torrents": ("x.torrent", marked, "application/x-bittorrent")},
    )


def test_mark_round_trip():
    data, info_hash = make_torrent(TOPIC, NIA_FILES)
    marked = torrent.mark(data, RELEASE)
    assert torrent.read(marked).info_hash != info_hash
    assert torrent.read(marked).files == torrent.read(data).files
    assert torrent.unmark(marked) == (data, RELEASE)
    assert torrent.unmark(data) == (data, None)
    remarked = torrent.mark(marked, "Other S01 -RuTracker")
    assert torrent.unmark(remarked) == (data, "Other S01 -RuTracker")


def test_file_tag():
    assert file_tag(RELEASE) == "OrigAudio OrigSoftSubs RusVoice RusSoftSubs RTA-T1 -RuTracker"
    tag = file_tag(RELEASE)
    assert tagged("A/Ep 01.mkv", tag) == f"A/Ep 01 {tag}.mkv"
    assert tagged(f"A/Ep 01 {tag}.mkv", tag) == f"A/Ep 01 {tag}.mkv"
    assert tagged("A/RUS Sound/Ep 01.mka", tag) == "A/RUS Sound/Ep 01.mka"


def test_served_unmarked_without_proxy(api, net):  # noqa: F811
    data, served = serve(api, net)
    assert served == data


def test_proxy_needs_login(api, qbit):  # noqa: F811
    assert api.get("/qbit/api/v2/app/webapiVersion").status_code == 403
    login(api)
    assert api.get("/qbit/api/v2/app/webapiVersion").text == "2.11.4"


def test_bearer_api_key(api, qbit):  # noqa: F811
    r = api.get("/qbit/api/v2/app/webapiVersion", headers={"Authorization": f"Bearer {key(api)}"})
    assert r.text == "2.11.4"


def test_add_rename_start_and_virtual_view(api, net, qbit):  # noqa: F811
    data, marked = serve(api, net)
    real = torrent.read(data).info_hash.lower()
    virtual = torrent.read(marked).info_hash.lower()
    assert marked != data
    login(api)
    assert add(api, marked).text == "Ok."

    # The real topic went to qBittorrent: unmarked, added stopped, renamed, then started.
    assert len(qbit.added) == 1 and qbit.added[0]["hash"] == real and qbit.added[0]["data"] == data
    assert qbit.added[0]["fields"]["stopped"] == "true"
    assert qbit.added[0]["fields"]["category"] == CATEGORY
    assert qbit.calls.index("torrents/renameFile") < qbit.calls.index("torrents/start")
    tag = file_tag(RELEASE)
    videos = [f for f in qbit.files[real] if f.endswith(".mkv")]
    assert videos and all(f.endswith(f" {tag}.mkv") for f in videos)
    assert not any(tag in f for f in qbit.files[real] if not f.endswith(".mkv"))
    assert qbit.torrents[real]["state"] == "downloading"

    # Sonarr sees the release, not the topic.
    items = api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json()
    assert [(t["hash"], t["name"], t["category"]) for t in items] == [(virtual, RELEASE, CATEGORY)]
    assert items[0]["content_path"] == f"/data/torrents/sonarr/{TOPIC}"
    props = api.get("/qbit/api/v2/torrents/properties", params={"hash": virtual}).json()
    assert props["hash"] == virtual and props["seeding_time"] == 5
    files = api.get("/qbit/api/v2/torrents/files", params={"hash": virtual}).json()
    assert [f["name"] for f in files] == qbit.files[real]

    # Finished and stopped: still reported seeding, so Sonarr doesn't move the files.
    qbit.torrents[real] |= {"state": "stoppedUP", "progress": 1.0}
    items = api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json()
    assert items[0]["state"] == "stalledUP"

    # The import script finds the companions of the renamed episode.
    ep2 = f"{NIA.format(n=2, crc=CRC[2])} {tag}.mkv"
    r = api.get(
        "/torznab/companions",
        params={
            "hash": virtual,
            "source": f"/data/torrents/sonarr/{TOPIC}/{ep2}",
            "apikey": key(api),
        },
    )
    assert r.status_code == 200, r.text
    lines = [line.split("\t") for line in r.text.splitlines()]
    assert lines[0] == ["#video", ep2]
    assert "ru.StudioBand.mka" in [s for _, s in lines[1:]]


def test_add_stopped_stays_stopped(api, net, qbit):  # noqa: F811
    data, marked = serve(api, net)
    login(api)
    assert add(api, marked, stopped="true").text == "Ok."
    assert "torrents/start" not in qbit.calls
    assert qbit.torrents[torrent.read(data).info_hash.lower()]["state"] == "stoppedDL"


def test_second_release_reuses_topic(api, net, qbit):  # noqa: F811
    data, first = serve(api, net)
    login(api)
    add(api, first)
    _, second = serve(api, net, name=RELEASE.replace("S01", "S01E02"))
    assert add(api, second).text == "Ok."
    assert len(qbit.added) == 1  # the topic is added once
    items = api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json()
    assert len(items) == 2 and {t["name"] for t in items} == {
        RELEASE,
        RELEASE.replace("S01", "S01E02"),
    }

    # Removing one release keeps the topic; removing the last one removes it.
    real = torrent.read(data).info_hash.lower()
    api.post(
        "/qbit/api/v2/torrents/delete", data={"hashes": items[0]["hash"], "deleteFiles": "false"}
    )
    assert real in qbit.torrents
    api.post(
        "/qbit/api/v2/torrents/delete", data={"hashes": items[1]["hash"], "deleteFiles": "true"}
    )
    assert real not in qbit.torrents and f"delete:{real}:true" in qbit.calls
    assert api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json() == []


def test_set_category_moves_the_release_and_its_topic(api, net, qbit):  # noqa: F811
    data, marked = serve(api, net)
    login(api)
    add(api, marked)
    virtual = torrent.read(marked).info_hash.lower()
    r = api.post(
        "/qbit/api/v2/torrents/setCategory", data={"hashes": virtual, "category": "imported"}
    )
    assert r.status_code == 200
    assert api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json() == []
    items = api.get("/qbit/api/v2/torrents/info", params={"category": "imported"}).json()
    assert [t["hash"] for t in items] == [virtual]
    # Its only release moved: the topic follows (hidden from both views either way).
    assert qbit.torrents[torrent.read(data).info_hash.lower()]["category"] == "imported"


def test_other_torrents_pass_through(api, net, qbit):  # noqa: F811
    login(api)
    plain, plain_hash = make_torrent("Some Other Show S01", ["e1.mkv"])
    assert add(api, plain).text == "Ok."
    h = plain_hash.lower()
    assert qbit.files[h] == ["Some Other Show S01/e1.mkv"]  # not renamed
    items = api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json()
    assert [t["hash"] for t in items] == [h]
    api.post("/qbit/api/v2/torrents/topPrio", data={"hashes": h})
    assert qbit.calls[-1] == "torrents/topPrio"
    assert (
        json.loads(api.get("/qbit/api/v2/torrents/properties", params={"hash": h}).text)["hash"]
        == h
    )


def test_old_qbittorrent_login(api, qbit):  # noqa: F811
    qbit.modern_login = False  # qBittorrent < 5.2: 200 "Ok."
    login(api)
    assert api.get("/qbit/api/v2/app/webapiVersion").text == "2.11.4"


def test_topic_follows_releases_to_post_import_category(api, net, qbit):  # noqa: F811
    data, first = serve(api, net)
    login(api)
    add(api, first)
    _, second = serve(api, net, name=RELEASE.replace("S01", "S01E02"))
    add(api, second)
    real = torrent.read(data).info_hash.lower()
    v1, v2 = (torrent.read(m).info_hash.lower() for m in (first, second))
    done = "sonarr/completed"

    # One release imported: the topic stays (the other still uses it).
    api.post("/qbit/api/v2/torrents/setCategory", data={"hashes": v1, "category": done})
    assert qbit.torrents[real]["category"] == CATEGORY
    # All imported: the topic follows.
    api.post("/qbit/api/v2/torrents/setCategory", data={"hashes": v2, "category": done})
    assert qbit.torrents[real]["category"] == done
    assert api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json() == []

    # A new release of the topic: back to the download category, not added again.
    _, third = serve(api, net, name=RELEASE.replace("S01", "S01E03"))
    assert add(api, third).text == "Ok."
    assert len(qbit.added) == 1
    assert qbit.torrents[real]["category"] == CATEGORY
    items = api.get("/qbit/api/v2/torrents/info", params={"category": CATEGORY}).json()
    assert [t["name"] for t in items] == [RELEASE.replace("S01", "S01E03")]


def test_qui_mode_goes_through_the_proxy_without_login(api, net):  # noqa: F811
    calls = []

    def version(request):
        calls.append(request.url.path)
        return httpx.Response(200, text="v5.2.4")

    net.on("GET", "/proxy/tok123/api/v2/app/version", version)
    net.on(
        "POST",
        "/proxy/tok123/api/v2/auth/login",
        lambda r: calls.append("login") or httpx.Response(204),
    )
    api.put(
        "/api/settings",
        json={
            "values": {
                "qbittorrent.mode": "qui",
                "qui.url": "http://qui:7476/",
                "qui.token": "tok123",
            }
        },
    )
    assert api.post("/api/arr/qbittorrent/test").json() == {
        "app": "qBittorrent",
        "version": "v5.2.4",
    }
    r = api.get("/api/status/connections", params={"refresh": "true"}).json()
    assert next(c for c in r["items"] if c["id"] == "qbittorrent")["state"] == "ok"
    assert "login" not in calls and calls  # no qBittorrent login through qui
    # Unsaved values from the form win.
    net.on("GET", "/proxy/other/api/v2/app/version", httpx.Response(403))
    bad = api.post("/api/arr/qbittorrent/test", json={"qui_token": "other"})
    assert bad.status_code == 502 and "qui URL and token" in bad.json()["detail"]


def test_untagged_and_old_tokens():
    from rutrackarr.releases.naming import file_tag, untagged

    old = "Show/Ep 01 [1080p] OrigAudio OrigSubs RusVoice RusSubs RTA-T1 -RuTracker.mkv"  # < v0.13
    new = "Show/Ep 01 [1080p] OrigAudio OrigSoftSubs RusSoftSubs RTA-T1 RTA-QC -RuTracker.mkv"
    assert untagged(old) == untagged(new) == "Show/Ep 01 [1080p].mkv"
    assert untagged("Show/Ep 01.mkv") == "Show/Ep 01.mkv"
    assert file_tag("X OrigAudio OrigSubs RusSubs RTA-T1 -RuTracker").startswith(
        "OrigAudio OrigSubs RusSubs"
    )


def test_radarr_does_not_take_soft_subs_for_hardcoded():
    import re

    # Radarr's Parser.HardcodedSubsRegex (src/NzbDrone.Core/Parser/Parser.cs)
    hc = re.compile(
        r"\b((?P<hcsub>(\w+(?<!SOFT)(?<!MULTI)(?<!HORRIBLE)SUBS?))|(?P<hc>(HC|SUBBED)))\b", re.I
    )
    new = "X 2005 1080p BluRay OrigAudio OrigSoftSubs RusVoice RusSoftSubs EngSoftSubs RTA-T1"
    assert not hc.search(new)
    assert hc.search("X 2005 OrigAudio RusSubs RTA-T1 -RuTracker")  # old tokens: taken for hardsubs
