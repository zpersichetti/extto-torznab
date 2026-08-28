from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from extto_torznab.models import Torrent
from extto_torznab.xml import TORZNAB_NS, render_caps, render_feed


def torrent() -> Torrent:
    return Torrent(
        id="123",
        slug="example-release",
        title="Example & Release",
        size=1024,
        files=2,
        published=datetime(2025, 8, 9, tzinfo=UTC),
        seeders=7,
        leechers=3,
        category=2000,
        magnet="magnet:?xt=urn:btih:ABC&dn=Example",
    )


def test_feed_is_namespaced_newznab_xml() -> None:
    root = ET.fromstring(render_feed([torrent()], "https://extto.com"))
    item = root.find("./channel/item")
    assert root.attrib["version"] == "2.0"
    assert item is not None
    assert item.findtext("title") == "Example & Release"
    assert item.findtext("guid") == "123"
    assert item.findtext("link") == "https://extto.com/example-release-123/"
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib == {
        "url": "magnet:?xt=urn:btih:ABC&dn=Example",
        "length": "1024",
        "type": "application/x-bittorrent",
    }
    attrs = {
        node.attrib["name"]: node.attrib["value"] for node in item.findall(f"{{{TORZNAB_NS}}}attr")
    }
    assert attrs == {"seeders": "7", "peers": "10", "leechers": "3", "category": "2000"}


def test_caps_advertises_search_and_categories() -> None:
    root = ET.fromstring(render_caps())
    assert root.find("./searching/search").attrib["supportedParams"] == "q"
    categories = {
        node.attrib["id"]: node.attrib["name"] for node in root.findall("./categories/category")
    }
    assert categories["5070"] == "Anime"
    assert categories["7000"] == "Books"
