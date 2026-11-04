from rutrackarr.rutracker import parse
from rutrackarr.rutracker.client import search_term
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
