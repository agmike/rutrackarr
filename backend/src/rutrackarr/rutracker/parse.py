"""HTML parsing of RuTracker pages (login form, login state, search results)."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
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


MAINTENANCE_MARKERS = ("временно отключен", "профилактическ")


def maintenance_message(html: str) -> str | None:
    """RuTracker's maintenance notice ("Форум временно отключен на профилактические работы…")."""
    if not any(m in html.lower() for m in MAINTENANCE_MARKERS):
        return None
    if 'id="logged-in-username"' in html or 'id="tor-tbl"' in html:
        return None  # a normal page that merely mentions the words (e.g. in a release title)
    tree = HTMLParser(html)
    for sel in ("h1", "h2", "h3", ".msg-main", "body"):
        node = tree.css_first(sel)
        text = _text(node)
        if text and any(m in text.lower() for m in MAINTENANCE_MARKERS):
            return text[:300]
    return "RuTracker is temporarily unavailable"


class PageKind(StrEnum):
    """What a RuTracker page positively shows (Cloudflare challenges are handled earlier)."""

    MAINTENANCE = "maintenance"
    LOGGED_IN = "logged_in"
    CAPTCHA = "captcha"
    LOGIN_FORM = "login_form"
    UNKNOWN = "unknown"


def classify(html: str) -> PageKind:
    if maintenance_message(html):
        return PageKind.MAINTENANCE
    tree = HTMLParser(html)
    if tree.css_first("#logged-in-username"):
        return PageKind.LOGGED_IN
    if captcha(html):
        return PageKind.CAPTCHA
    if tree.css_first('input[name="login_username"]') and tree.css_first(
        'input[name="login_password"]'
    ):
        return PageKind.LOGIN_FORM
    return PageKind.UNKNOWN


def page_summary(html: str, status: int) -> str:
    """Short description of an unrecognised page for error messages / diagnosis."""
    tree = HTMLParser(html)
    title = _text(tree.css_first("title")) or "no title"
    body = _text(tree.css_first("body"))[:200]
    return f"HTTP {status}, title {title!r}" + (f": {body}" if body else "")


def logged_in_user(html: str) -> str | None:
    node = HTMLParser(html).css_first("#logged-in-username")
    return _text(node) or None if node else None


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
    return _text(node) or None if node else None


def _text(node: Node | None) -> str:
    """Visible text with original spacing; whitespace runs collapsed.

    (`text(strip=True)` strips each text node separately and would glue
    "Door 2 " + "[TV]" into "Door 2[TV]".)
    """
    if node is None:
        return ""
    return " ".join(node.text(deep=True, separator="", strip=False).split())


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
                title=_text(link),
                forum_id=_query_int(forum.attributes.get("href"), "f") if forum else None,
                forum=_text(forum),
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


@dataclass(frozen=True)
class Forum:
    forum_id: int
    name: str
    parent_id: int | None  # None for a top-level section
    group: str  # the dropdown's group ("Кино, Видео и ТВ", "Сериалы", …)


def forums(html: str) -> list[Forum]:
    """RuTracker's section list, from the search form's dropdown (on every tracker.php page)."""
    tree = HTMLParser(html)
    select = tree.css_first("select#fs-main")
    if select is None:
        return []
    out: list[Forum] = []
    for group in select.css("optgroup"):
        label = " ".join((group.attributes.get("label") or "").split())
        root: int | None = None
        for opt in group.css("option"):
            value = (opt.attributes.get("value") or "").strip()
            if not value.isdigit():
                continue
            fid = int(value)
            cls = opt.attributes.get("class") or ""
            name = _text(opt).replace("|-", "", 1).strip()
            if "root_forum" in cls:
                root = fid
                out.append(Forum(fid, name, None, label))
            else:
                parent = next(
                    (int(c[3:]) for c in cls.split() if c.startswith("fp-") and c[3:].isdigit()),
                    root,
                )
                out.append(Forum(fid, name, parent, label))
    return out


@dataclass(frozen=True)
class TopicInfo:
    title: str
    forum: str
    forum_id: int | None


_FORUM_LINK = re.compile(r"viewforum\.php\?f=(\d+)")
_TITLE_SUFFIX = re.compile(r"\s*::\s*RuTracker\.org\s*$", re.I)


def topic_info(html: str) -> TopicInfo | None:
    """A topic page's title and section: the topic heading (or the page <title> without
    " :: RuTracker.org"), and the last section link of the breadcrumbs."""
    tree = HTMLParser(html)
    heading = tree.css_first("#topic-title") or tree.css_first("h1.maintitle a")
    title = _text(heading) if heading is not None else ""
    if not title and (t := tree.css_first("title")) is not None:
        title = _TITLE_SUFFIX.sub("", _text(t))
    if not title:
        return None
    # Breadcrumbs: index › category › section › subsection; the last one is the topic's.
    crumbs: list[Node] = []
    for selector in (".t-breadcrumb-top a", ".nav a"):
        crumbs = [
            a for a in tree.css(selector) if _FORUM_LINK.search(a.attributes.get("href") or "")
        ]
        if crumbs:
            break
    forum, forum_id = "", None
    if crumbs:
        forum = _text(crumbs[-1])
        m = _FORUM_LINK.search(crumbs[-1].attributes.get("href") or "")
        forum_id = int(m.group(1)) if m else None
    return TopicInfo(title, forum, forum_id)
