from rutrackarr.rutracker import parse
from rutrackarr.rutracker.client import search_term
from rutrackarr.rutracker.parse import PageKind
from tests.fixtures import pages


def test_search_term_wildcards():
    assert search_term("Re:Zero — Жизнь с нуля!") == "Re%Zero%Жизнь%с%нуля"
    assert search_term("  ") == ""


def test_search_rows():
    rows = parse.search_rows(pages.search_page(pages.ROW_HYOUKA + pages.ROW_NOT_FOUND))
    assert len(rows) == 1
    r = rows[0]
    assert r.topic_id == 4211111
    assert r.title.startswith("Хёка / Hyouka [TV]") and "JAP+Sub" in r.title
    assert (r.forum_id, r.forum) == (1105, "Аниме (HD Video)")
    assert (r.size, r.seeders, r.leechers, r.downloads) == (15032385536, 42, 3, 1234)
    assert r.added is not None and r.added.year == 2023
    assert r.author == "uploader1" and r.approved == "проверено"


def test_login_state_captcha_error():
    assert parse.logged_in_user(pages.INDEX_LOGGED_IN) == "tester"
    assert parse.logged_in_user(pages.LOGIN_FORM) is None
    ch = parse.captcha(pages.LOGIN_FORM_CAPTCHA)
    assert ch and ch.sid == "SID123" and ch.code_field == "cap_code_deadbeef"
    assert parse.captcha(pages.LOGIN_FORM) is None
    assert parse.login_error(pages.LOGIN_WRONG) == "неверный пароль"


def test_title_spacing_kept_across_markup():
    (row,) = parse.search_rows(pages.search_page(pages.ROW_SPLIT_TITLE))
    assert row.title == (
        "Городская демонесса (ТВ-2) / Machikado Mazoku 2-Choume / The Demon Girl Next Door 2 "
        "[TV] [12 из 12] [JAP+Sub] [2022, Комедия, BDRemux] [1080p]"
    )


def test_maintenance_detection():
    assert "04:45" in parse.maintenance_message(pages.MAINTENANCE)
    row = pages.ROW_HYOUKA.replace("Хёка / Hyouka", "Профилактические работы / Hyouka")
    assert parse.maintenance_message(pages.search_page(row)) is None


def test_classify_is_positive():
    assert parse.classify(pages.MAINTENANCE) is PageKind.MAINTENANCE
    assert parse.classify(pages.INDEX_LOGGED_IN) is PageKind.LOGGED_IN
    assert parse.classify(pages.search_page(pages.ROW_HYOUKA)) is PageKind.LOGGED_IN
    assert parse.classify(pages.LOGIN_FORM_CAPTCHA) is PageKind.CAPTCHA
    assert parse.classify(pages.LOGIN_FORM) is PageKind.LOGIN_FORM
    assert parse.classify(pages.LOGIN_WRONG) is PageKind.LOGIN_FORM
    assert parse.classify(pages.search_page("", logged_in=False)) is PageKind.LOGIN_FORM
    # A results table without the username is not "logged in" — and not a login form either.
    assert parse.classify(pages.UNKNOWN) is PageKind.UNKNOWN
    assert parse.classify("") is PageKind.UNKNOWN
    assert (
        parse.classify("<html><body><table id='tor-tbl'></table></body></html>") is PageKind.UNKNOWN
    )


def test_page_summary():
    s = parse.page_summary(pages.UNKNOWN, 502)
    assert s.startswith("HTTP 502, title '502 Bad Gateway'") and "nginx" in s
    assert parse.page_summary("", 200) == "HTTP 200, title 'no title'"
