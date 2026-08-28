from pathlib import Path

import pytest

from extto_torznab.parser import ParseError, extract_tokens, parse_browse, parse_size

FIXTURE = Path(__file__).parents[1] / "research/fixtures/browse_ubuntu_24_04.html"


def test_extracts_session_bound_tokens() -> None:
    tokens = extract_tokens(FIXTURE.read_text())
    assert tokens.page_token == "31db34d4de129bc16fb0a000743a3efc"
    assert tokens.csrf_token == "8b79a879634e6c600c384f044ae4ab43"


def test_rejects_tokenless_ajax_fragment() -> None:
    with pytest.raises(ParseError):
        extract_tokens('<table class="search-table"></table>')


def test_parses_real_browse_fixture() -> None:
    page = parse_browse(FIXTURE.read_text())
    assert len(page.results) == 12
    first = page.results[0]
    assert first.id == "16276717"
    assert first.slug == "the-ultimate-ubuntu-handbook-a-complete-guide-to-ubuntu-24-04-true-pdf"
    assert first.title == (
        "The Ultimate Ubuntu Handbook: A complete guide to Ubuntu 24.04 (True PDF)"
    )
    assert first.size == 11_513_364
    assert first.files == 1
    assert first.published.year == 2025
    assert first.published.month == 8
    assert first.published.day == 9
    assert first.seeders == 41
    assert first.leechers == 1
    assert first.category == 7000


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1 KB", 1024), ("1.5 MB", 1_572_864), ("2 GB", 2_147_483_648), ("3 TB", 3_298_534_883_328)],
)
def test_parse_size(text: str, expected: int) -> None:
    assert parse_size(text) == expected
