from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

import httpx
import pytest

from extto_torznab.app import create_app
from extto_torznab.models import Torrent


class FakeUpstream:
    def __init__(self) -> None:
        self.last_success = datetime.now(UTC)
        self.search_args = None

    async def bootstrap(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def search(self, query: str, category: int | None = None) -> list[Torrent]:
        self.search_args = (query, category)
        return [
            Torrent(
                id="123",
                slug="release",
                title="Release",
                size=10,
                files=1,
                published=datetime(2025, 1, 2, tzinfo=UTC),
                seeders=2,
                leechers=1,
                category=category or 8000,
                magnet="magnet:?xt=urn:btih:ABC",
            )
        ]

    async def detail(self, torrent_id: str) -> Torrent | None:
        results = await self.search(torrent_id)
        return results[0] if torrent_id == "123" else None


@asynccontextmanager
async def client(api_key: str = "secret") -> AsyncIterator[tuple[httpx.AsyncClient, FakeUpstream]]:
    upstream = FakeUpstream()
    app = create_app(api_key=api_key, upstream=upstream)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, upstream


@pytest.mark.parametrize("params", [{"t": "caps"}, {"t": "caps", "apikey": "wrong"}])
async def test_api_key_is_required(params: dict[str, str]) -> None:
    async with client() as (ac, _):
        assert (await ac.get("/api", params=params)).status_code == 401


async def test_caps() -> None:
    async with client() as (ac, _):
        response = await ac.get("/api", params={"t": "caps", "apikey": "secret"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert ET.fromstring(response.content).tag == "caps"


async def test_search_maps_newznab_category() -> None:
    async with client() as (ac, upstream):
        response = await ac.get(
            "/api", params={"t": "search", "q": "ubuntu", "cat": "4000", "apikey": "secret"}
        )
    assert response.status_code == 200
    assert upstream.search_args == ("ubuntu", 4000)
    assert ET.fromstring(response.content).findtext("./channel/item/guid") == "123"


async def test_search_requires_query() -> None:
    async with client() as (ac, _):
        response = await ac.get("/api", params={"t": "search", "apikey": "secret"})
    assert response.status_code == 400


async def test_detail_and_health() -> None:
    async with client() as (ac, _):
        detail = await ac.get("/api", params={"t": "detail", "id": "123", "apikey": "secret"})
        health = await ac.get("/healthz")
    assert detail.status_code == 200
    assert ET.fromstring(detail.content).findtext("./channel/item/guid") == "123"
    assert health.status_code == 200
