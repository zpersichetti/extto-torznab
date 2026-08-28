from email.utils import format_datetime
from xml.etree import ElementTree as ET

from .categories import CATEGORIES
from .models import Torrent

TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
ET.register_namespace("torznab", TORZNAB_NS)


def render_caps() -> bytes:
    root = ET.Element("caps")
    ET.SubElement(root, "server", title="EXT Torrents", version="0.1.0")
    limits = ET.SubElement(root, "limits", max="50", default="50")
    limits.tail = None
    searching = ET.SubElement(root, "searching")
    ET.SubElement(searching, "search", available="yes", supportedParams="q")
    ET.SubElement(searching, "tv-search", available="no", supportedParams="")
    ET.SubElement(searching, "movie-search", available="no", supportedParams="")
    ET.SubElement(searching, "audio-search", available="no", supportedParams="")
    ET.SubElement(searching, "book-search", available="no", supportedParams="")
    categories = ET.SubElement(root, "categories")
    for category in CATEGORIES:
        ET.SubElement(categories, "category", id=str(category.newznab_id), name=category.name)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def render_feed(torrents: list[Torrent], upstream_base: str) -> bytes:
    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = "EXT Torrents"
    ET.SubElement(channel, "description").text = "EXT Torrents Torznab results"
    ET.SubElement(channel, "link").text = upstream_base
    ET.SubElement(
        channel,
        f"{{{TORZNAB_NS}}}response",
        offset="0",
        total=str(len(torrents)),
    )
    for torrent in torrents:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = torrent.title
        ET.SubElement(item, "guid", isPermaLink="false").text = torrent.id
        detail_url = f"{upstream_base.rstrip('/')}/{torrent.slug}-{torrent.id}/"
        ET.SubElement(item, "link").text = detail_url
        ET.SubElement(item, "comments").text = detail_url
        ET.SubElement(item, "pubDate").text = format_datetime(torrent.published, usegmt=True)
        ET.SubElement(item, "size").text = str(torrent.size)
        ET.SubElement(item, "category").text = str(torrent.category)
        if torrent.magnet:
            ET.SubElement(
                item,
                "enclosure",
                url=torrent.magnet,
                length=str(torrent.size),
                type="application/x-bittorrent",
            )
        for name, value in (
            ("seeders", torrent.seeders),
            ("peers", torrent.seeders + torrent.leechers),
            ("leechers", torrent.leechers),
            ("category", torrent.category),
        ):
            ET.SubElement(item, f"{{{TORZNAB_NS}}}attr", name=name, value=str(value))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
