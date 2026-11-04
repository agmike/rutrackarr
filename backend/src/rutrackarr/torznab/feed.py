"""Torznab XML: capabilities, result feed, errors."""

from email.utils import format_datetime
from xml.etree import ElementTree as ET

from rutrackarr.torznab.search import Release

TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
ET.register_namespace("torznab", TORZNAB_NS)

CATEGORIES = {
    2000: ("Movies", {2030: "Movies/SD", 2040: "Movies/HD", 2045: "Movies/UHD"}),
    5000: ("TV", {5030: "TV/SD", 5040: "TV/HD", 5045: "TV/UHD", 5070: "TV/Anime"}),
}


def _xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def caps(version: str) -> bytes:
    root = ET.Element("caps")
    ET.SubElement(root, "server", version=version, title="RuTrackarr")
    ET.SubElement(root, "limits", max="100", default="100")
    searching = ET.SubElement(root, "searching")
    ET.SubElement(searching, "search", available="yes", supportedParams="q")
    ET.SubElement(searching, "tv-search", available="yes", supportedParams="q,season,ep")
    ET.SubElement(searching, "movie-search", available="yes", supportedParams="q")
    cats = ET.SubElement(root, "categories")
    for cid, (name, subs) in CATEGORIES.items():
        cat = ET.SubElement(cats, "category", id=str(cid), name=name)
        for sid, sname in subs.items():
            ET.SubElement(cat, "subcat", id=str(sid), name=sname)
    return _xml(root)


def error(code: int, description: str) -> bytes:
    return _xml(ET.Element("error", code=str(code), description=description))


def results(releases: list[Release], download_url, topic_url) -> bytes:  # type: ignore[no-untyped-def]
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "RuTrackarr"
    for rel in releases:
        row = rel.row
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = rel.name
        topic, link = topic_url(row.topic_id), download_url(row.topic_id)
        ET.SubElement(item, "guid", isPermaLink="true").text = topic
        ET.SubElement(item, "comments").text = topic
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "description").text = row.title
        if row.added:
            ET.SubElement(item, "pubDate").text = format_datetime(row.added)
        ET.SubElement(item, "size").text = str(row.size)
        for cid in rel.categories:
            ET.SubElement(item, "category").text = str(cid)
        ET.SubElement(
            item, "enclosure", url=link, length=str(row.size), type="application/x-bittorrent"
        )
        attrs = {
            "seeders": row.seeders,
            "peers": row.seeders + row.leechers,
            "grabs": row.downloads,
            "downloadvolumefactor": 1,
            "uploadvolumefactor": 1,
        }
        for cid in rel.categories:
            ET.SubElement(item, f"{{{TORZNAB_NS}}}attr", name="category", value=str(cid))
        for name, value in attrs.items():
            ET.SubElement(item, f"{{{TORZNAB_NS}}}attr", name=name, value=str(value))
    return _xml(rss)
