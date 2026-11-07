"""Which file of a pack is episode N."""

from rutrackarr.releases.episodes import episode_file, episode_numbers

SXXEYY = [f"Show/Show.S02E{n:02d}.1080p.WEB-DL.mkv" for n in range(1, 7)]
FANSUB = [
    f"Show/[SubsPlus+] Show - {n:02d} (ADN WEB-DL 1080p AVC AAC) [{c}].mkv"
    for n, c in ((1, "4EFEF51F"), (2, "333EA23D"), (3, "0B5C42D7"))
]
PLAIN = [f"Show/{n:02d}. Some title.mkv" for n in range(13, 16)]
EXTRAS = [
    *FANSUB,
    "Show/Extras/NCOP 01.mkv",
    "Show/[SubsPlus+] Show - NCED (1080p).mkv",
    "Show/RUS Sound/[SubsPlus+] Show - 01.mka",
]


def test_explicit_episode_numbers():
    assert episode_file(SXXEYY, 4) == "Show/Show.S02E04.1080p.WEB-DL.mkv"


def test_the_number_that_varies():
    assert episode_numbers(FANSUB) == {
        1: FANSUB[0],
        2: FANSUB[1],
        3: FANSUB[2],
    }  # not 1080, not the CRC
    assert episode_file(PLAIN, 14, 13, 15) == "Show/14. Some title.mkv"


def test_extras_and_companions_are_ignored():
    assert episode_numbers(EXTRAS) == {1: FANSUB[0], 2: FANSUB[1], 3: FANSUB[2]}


def test_order_when_names_say_nothing():
    files = ["S/a.mkv", "S/b.mkv", "S/c.mkv"]
    assert episode_file(files, 6, 5, 7) == "S/b.mkv"
    assert episode_file(files, 6) is None  # can't tell without the range


def test_one_file():
    assert episode_file(["Film.mkv"], 7, 7, 7) == "Film.mkv"
