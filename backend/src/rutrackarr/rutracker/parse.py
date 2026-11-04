"""HTML parsing of RuTracker pages (login form, login state, search results)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from selectolax.lexbor import LexborHTMLParser as HTMLParser
from selectolax.lexbor import LexborNode as Node


@dataclass
class CaptchaChallenge:
    image_url: str
    sid: str
    code_field: str


@dataclass
class SearchRow:
    topic_id: int
    title: str
    forum_id: int | None
    forum: str
    size: int
    seeders: int
    leechers: int
    downloads: int
    added: datetime | None
    author: str
    approved: str | None  # status icon title, e.g. "проверено"


def logged_in_user(html: str) -> str | None:
    node = HTMLParser(html).css_first("#logged-in-username")
    return node.text(strip=True) if node else None


def captcha(html: str) -> CaptchaChallenge | None:
    tree = HTMLParser(html)
    img = tree.css_first('img[src*="/captcha/"]')
    sid = tree.css_first('input[name="cap_sid"]')
    code = tree.css_first('input[name^="cap_code_"]')
    if not (img and sid and code):
        return None
    src = img.attributes.get("src") or ""
    if src.startswith("//"):
        src = "https:" + src
    return CaptchaChallenge(
        src, sid.attributes.get("value") or "", code.attributes.get("name") or ""
    )


def login_error(html: str) -> str | None:
    node = HTMLParser(html).css_first("h4.warnColor1, div.msg-main, .mrg_16.warnColor1")
    return node.text(strip=True) if node else None


def _int(text: str | None) -> int:
    digits = "".join(ch for ch in (text or "") if ch.isdigit() or ch == "-")
    try:
        return int(digits)
    except ValueError:
        return 0


def _query_int(href: str | None, key: str) -> int | None:
    if not href:
        return None
    values = parse_qs(urlparse(href).query).get(key)
    return int(values[0]) if values and values[0].isdigit() else None


def _cell(row: Node, n: int) -> Node | None:
    cells = row.css("td")
    return cells[n - 1] if len(cells) >= n else None


def search_rows(html: str) -> list[SearchRow]:
    rows: list[SearchRow] = []
    for tr in HTMLParser(html).css("table#tor-tbl > tbody > tr"):
        link = tr.css_first("a.tLink")
        if link is None:
            continue  # "nothing found" row
        topic_id = _query_int(link.attributes.get("href"), "t")
        if topic_id is None:
            continue
        forum = tr.css_first("td.f-name-col a") or tr.css_first(".f-name a")
        size_cell = tr.css_first("td.tor-size")
        seeders_cell = _cell(tr, 7)
        seed_b = seeders_cell.css_first("b") if seeders_cell else None
        added_cell = _cell(tr, 10)
        added_ts = added_cell.attributes.get("data-ts_text") if added_cell else None
        status = tr.css_first("td.t-ico span[title], td.t-ico [title]")
        rows.append(
            SearchRow(
                topic_id=topic_id,
                title=link.text(strip=True),
                forum_id=_query_int(forum.attributes.get("href"), "f") if forum else None,
                forum=forum.text(strip=True) if forum else "",
                size=_int(size_cell.attributes.get("data-ts_text")) if size_cell else 0,
                seeders=_int(
                    seed_b.text() if seed_b else (seeders_cell.text() if seeders_cell else "")
                ),
                leechers=_int(_cell(tr, 8).text() if _cell(tr, 8) else ""),
                downloads=_int(_cell(tr, 9).text() if _cell(tr, 9) else ""),
                added=datetime.fromtimestamp(int(added_ts), UTC)
                if added_ts and added_ts.isdigit()
                else None,
                author=(
                    tr.css_first("td.u-name-col").text(strip=True)
                    if tr.css_first("td.u-name-col")
                    else ""
                ),
                approved=status.attributes.get("title") if status else None,
            )
        )
    return rows
