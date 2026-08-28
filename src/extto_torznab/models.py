from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Tokens:
    page_token: str
    csrf_token: str


@dataclass(frozen=True, slots=True)
class Torrent:
    id: str
    slug: str
    title: str
    size: int
    files: int
    published: datetime
    seeders: int
    leechers: int
    category: int
    magnet: str | None = None

    def with_magnet(self, magnet: str) -> "Torrent":
        return replace(self, magnet=magnet)
