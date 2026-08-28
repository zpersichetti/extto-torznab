import re
from dataclasses import dataclass
from datetime import UTC, datetime

from bs4 import BeautifulSoup, Tag

from .categories import NAME_TO_NEWZNAB
from .models import Tokens, Torrent


class ParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BrowsePage:
    tokens: Tokens
    results: list[Torrent]


TOKEN_RE = re.compile(r"searchPageToken\s*=\s*['\"]([0-9a-f]{32})['\"]", re.IGNORECASE)
TORRENT_PATH_RE = re.compile(r"^/(.+)-(\d+)/$")
SIZE_RE = re.compile(r"^\s*([\d.]+)\s*([KMGT]?B)\s*$", re.IGNORECASE)


def extract_tokens(html: str) -> Tokens:
    page_token = TOKEN_RE.search(html)
    soup = BeautifulSoup(html, "html.parser")
    csrf = soup.find("meta", attrs={"name": "csrf-token"})
    csrf_value = csrf.get("content") if isinstance(csrf, Tag) else None
    if (
        not page_token
        or not isinstance(csrf_value, str)
        or not re.fullmatch(r"[0-9a-fA-F]{32}", csrf_value)
    ):
        raise ParseError("browse response is missing session-bound page tokens")
    return Tokens(page_token.group(1), csrf_value)


def parse_size(value: str) -> int:
    match = SIZE_RE.match(value)
    if not match:
        raise ParseError(f"unsupported torrent size: {value!r}")
    amount, unit = match.groups()
    multiplier = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return round(float(amount) * multiplier[unit.upper()])


def _field(row: Tag, name: str) -> Tag | None:
    label = row.find("span", class_="add-block", string=lambda text: text and text.strip() == name)
    return label.find_next_sibling("span") if isinstance(label, Tag) else None


def _integer(row: Tag, name: str) -> int:
    node = _field(row, name)
    if node is None:
        return 0
    cleaned = node.get_text(strip=True).replace(",", "")
    return int(cleaned) if cleaned.isdigit() else 0


def _category(row: Tag) -> int:
    posted = row.find("div", class_="related-posted")
    if isinstance(posted, Tag):
        for link in posted.find_all("a", href=True):
            name = link.get_text(" ", strip=True).casefold()
            if name in NAME_TO_NEWZNAB:
                return NAME_TO_NEWZNAB[name]
    return 8000


def parse_browse(html: str) -> BrowsePage:
    tokens = extract_tokens(html)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.search-table")
    if table is None:
        raise ParseError("browse response has no results table")

    results: list[Torrent] = []
    for row in table.select("tbody tr"):
        title_link = row.select_one("a.torrent-title-link[href]")
        if not isinstance(title_link, Tag):
            continue
        href = title_link.get("href")
        match = TORRENT_PATH_RE.match(href) if isinstance(href, str) else None
        if not match:
            continue
        slug, torrent_id = match.groups()
        size_node = _field(row, "Size")
        age_node = _field(row, "Age")
        if size_node is None or age_node is None:
            continue
        age_title = age_node.get("title")
        if not isinstance(age_title, str):
            raise ParseError(f"torrent {torrent_id} has no exact age date")
        try:
            published = datetime.strptime(age_title, "%d %B %Y").replace(tzinfo=UTC)
        except ValueError as exc:
            raise ParseError(f"torrent {torrent_id} has invalid age date: {age_title!r}") from exc
        results.append(
            Torrent(
                id=torrent_id,
                slug=slug,
                title=" ".join(title_link.get_text("", strip=False).split()),
                size=parse_size(size_node.get_text(strip=True)),
                files=_integer(row, "Files"),
                published=published,
                seeders=_integer(row, "Seeds"),
                leechers=_integer(row, "Leechs"),
                category=_category(row),
            )
        )
    return BrowsePage(tokens=tokens, results=results)
