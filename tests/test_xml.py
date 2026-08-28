from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from extto_torznab.categories import ext_category_for
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
        magnet="magnet:?xt=urn:btih:15848D905FE653D6B179A3746C51B9EF7CD5D21F&dn=Example",
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
        "url": "magnet:?xt=urn:btih:15848D905FE653D6B179A3746C51B9EF7CD5D21F&dn=Example",
        "length": "1024",
        "type": "application/x-bittorrent",
    }
    attrs = {
        node.attrib["name"]: node.attrib["value"] for node in item.findall(f"{{{TORZNAB_NS}}}attr")
    }
    assert attrs == {
        "seeders": "7",
        "peers": "10",
        "leechers": "3",
        "category": "2000",
        "magneturl": "magnet:?xt=urn:btih:15848D905FE653D6B179A3746C51B9EF7CD5D21F&dn=Example",
        "infohash": "15848D905FE653D6B179A3746C51B9EF7CD5D21F",
    }


def test_caps_advertises_search_and_categories() -> None:
    root = ET.fromstring(render_caps())
    assert root.find("./searching/search").attrib["supportedParams"] == "q"
    categories = {
        node.attrib["id"]: node.attrib["name"] for node in root.findall("./categories/category")
    }
    assert categories["2000"] == "Movies"
    assert categories["5000"] == "TV"
    assert categories["3000"] == "Audio"
    assert categories["7000"] == "Books"
    subcats = {
        node.attrib["id"]: node.attrib["name"]
        for node in root.findall("./categories/category/subcat")
    }
    assert subcats["5070"] == "Anime"
    assert subcats["3030"] == "Audiobook"
    assert subcats["7020"] == "EBook"


def test_subcategories_map_to_sections() -> None:
    # Top-level categories pass through.
    assert ext_category_for(2000) == 1
    assert ext_category_for(7000) == 6
    # Subcategories resolve to their parent section...
    assert ext_category_for(5040) == 2  # TV/HD -> TV
    assert ext_category_for(3010) == 3  # Audio/MP3 -> Audio
    assert ext_category_for(7010) == 6  # Books/Magazines -> Books
    # ...with two extto.com layout exceptions.
    assert ext_category_for(3030) == 6  # audiobook -> Books (not Audio)
    assert ext_category_for(5070) == 7  # anime -> dedicated Anime section
    # Unknown categories fall back to the parent section, then nothing.
    assert ext_category_for(3090) == 3  # unknown audio subcat -> Audio
    assert ext_category_for(9999) is None
    assert ext_category_for(None) is None
