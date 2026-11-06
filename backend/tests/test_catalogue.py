"""RuTracker's section dropdown → catalogue → video-only searches."""

from rutrackarr.releases.sections import Catalogue
from rutrackarr.rutracker import parse
from tests.fixtures import pages
from tests.test_rutracker_flow import api, html, net  # noqa: F401  (fixtures)
from tests.test_torznab import key


def test_parse_forums():
    forums = parse.forums(f"<html><body>{pages.FORUM_SELECT}</body></html>")
    by_id = {f.forum_id: f for f in forums}
    assert len(forums) == 11
    assert by_id[187] == parse.Forum(187, "Классика мирового кинематографа", 7, "Кино, Видео и ТВ")
    assert by_id[22].parent_id is None and by_id[499].group == "Аудиокниги"


def test_catalogue_inherits_parent_kind():
    cat = Catalogue(parse.forums(pages.FORUM_SELECT))
    s = cat.sections
    assert (s[187].video, s[187].label) == (True, "foreign movie")  # no "кино"/"фильм" in its name
    assert s[941].label == "russian movie"  # "Кино СССР" under "Наше кино"
    assert s[842].label == "foreign series"  # "Новинки…" under "Зарубежные сериалы"
    assert s[2544].label == "anime anime"
    assert not s[185].video and not s[499].video
    assert cat.video_ids() == [7, 22, 33, 187, 189, 842, 941, 2093, 2544]
    # Unknown ids fall back to the name.
    assert cat.section(None, "Аниме (HD Video)").label == "anime anime"


def test_searches_use_video_sections_once_known(api, net):  # noqa: F811
    first = pages.search_page(
        pages.row(
            1,
            "Шерлок / Sherlock (Р) [2010, WEB-DL 1080p] MVO",
            "Классика мирового кинематографа",
            forum_id=187,
        )
    )
    net.on(
        "GET", "/forum/tracker.php", html(first.replace("</body>", pages.FORUM_SELECT + "</body>"))
    )
    k = key(api)
    found = api.get("/torznab/api", params={"t": "search", "q": "Sherlock", "apikey": k})
    assert b"Sherlock" in found.content  # classified by section id: video
    api.get("/torznab/api", params={"t": "search", "q": "Interstellar", "apikey": k})
    searches = [c for c in net.calls if c.url.path == "/forum/tracker.php"]
    assert "f" not in searches[0].url.params  # nothing known yet
    assert searches[1].url.params["f"] == "7,22,33,187,189,842,941,2093,2544"
