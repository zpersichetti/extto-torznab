import asyncio
import hashlib
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from .categories import ext_category_for
from .config import Settings
from .models import Tokens, Torrent
from .parser import BrowsePage, ParseError, parse_browse

LOGGER = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)


class UpstreamError(RuntimeError):
    pass


def sign_magnet_request(torrent_id: str, timestamp: int, page_token: str) -> str:
    payload = f"{torrent_id}|{timestamp}|{page_token}".encode()
    return hashlib.sha256(payload).hexdigest()


class ExtToClient:
    """Serialized, paced extto.com browser session and magnet signer."""

    def __init__(
        self,
        settings: Settings,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self._clock = clock
        self._wall_clock = wall_clock
        self._workflow_lock = asyncio.Lock()
        self._last_request_started: float | None = None
        self._client = self._new_client()
        self._tokens: Tokens | None = None
        self._referer: str | None = None
        self._browse_context: tuple[str, int | None] = ("", None)
        self._magnet_cache: dict[str, tuple[float, str]] = {}
        self._torrent_cache: dict[str, Torrent] = {}
        self.last_success: datetime | None = None

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.upstream_base,
            headers={"User-Agent": USER_AGENT},
            timeout=self.settings.request_timeout,
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _rotate_session(self) -> None:
        old_client = self._client
        self._client = self._new_client()
        self._tokens = None
        self._referer = None
        await old_client.aclose()

    async def _paced_request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self._last_request_started is not None:
            elapsed = self._clock() - self._last_request_started
            if elapsed < self.settings.min_interval:
                await asyncio.sleep(self.settings.min_interval - elapsed)
        self._last_request_started = self._clock()
        return await self._client.request(method, url, **kwargs)

    async def _backoff(self, attempt: int) -> None:
        delay = min(self.settings.backoff_initial * (2**attempt), self.settings.backoff_cap)
        LOGGER.warning("extto.com request failed; retrying in %.1fs", delay)
        await asyncio.sleep(delay)

    async def _browse(self, query: str, ext_category: int | None = None) -> BrowsePage:
        params: dict[str, str | int] = {}
        if query:
            params["q"] = query
        params["page"] = 1
        params["page_size"] = 50
        if ext_category is not None:
            params["cat"] = ext_category
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                # Deliberately no X-Requested-With: full pages contain both tokens.
                response = await self._paced_request("GET", "/browse/", params=params)
                response.raise_for_status()
                page = parse_browse(response.text)
                self._tokens = page.tokens
                self._referer = str(response.request.url)
                self._browse_context = (query, ext_category)
                self.last_success = datetime.now(UTC)
                return page
            except (httpx.HTTPError, ParseError) as exc:
                last_error = exc
                await self._rotate_session()
                if attempt < 3:
                    await self._backoff(attempt)
        raise UpstreamError("could not obtain a parseable extto.com browse page") from last_error

    async def _magnet(self, torrent_id: str) -> str:
        cached = self._magnet_cache.get(torrent_id)
        if cached and self._clock() - cached[0] < self.settings.magnet_cache_ttl:
            return cached[1]

        last_error: Exception | None = None
        for attempt in range(3):
            if self._tokens is None or self._referer is None:
                await self._browse(*self._browse_context)
            assert self._tokens is not None
            assert self._referer is not None
            timestamp = int(self._wall_clock())
            form = {
                "torrent_id": torrent_id,
                "hash": "",
                "name": "",
                "timestamp": str(timestamp),
                "hmac": sign_magnet_request(torrent_id, timestamp, self._tokens.page_token),
                "sessid": self._tokens.csrf_token,
            }
            try:
                response = await self._paced_request(
                    "POST",
                    "/ajax/getSearchMagnet.php",
                    data=form,
                    headers={
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": self._referer,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                magnet = payload.get("url") if payload.get("success") is True else None
                if not isinstance(magnet, str) or not magnet.startswith("magnet:?xt=urn:btih:"):
                    raise UpstreamError("magnet endpoint returned an invalid response")
                self._magnet_cache[torrent_id] = (self._clock(), magnet)
                self.last_success = datetime.now(UTC)
                return magnet
            except (httpx.HTTPError, ValueError, UpstreamError) as exc:
                last_error = exc
                if attempt < 2:
                    await self._backoff(attempt)
                    await self._rotate_session()
                    await self._browse(*self._browse_context)
        raise UpstreamError(f"could not fetch magnet for torrent {torrent_id}") from last_error

    async def _probe(self) -> None:
        """Startup health probe: a 200 from the browse page is enough.

        Note: an EMPTY-query browse response carries no searchPageToken (the
        token is only emitted on real search pages), so the probe must not
        require parseable tokens — they are acquired lazily on first search.
        """
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = await self._paced_request(
                    "GET", "/browse/", params={"page": 1, "page_size": 1}
                )
                response.raise_for_status()
                self.last_success = datetime.now(UTC)
                return
            except httpx.HTTPError as exc:
                last_error = exc
                await self._rotate_session()
                if attempt < 3:
                    await self._backoff(attempt)
        raise UpstreamError("could not reach extto.com") from last_error

    async def bootstrap(self) -> None:
        async with self._workflow_lock:
            await self._probe()

    async def search(self, query: str, category: int | None = None) -> list[Torrent]:
        async with self._workflow_lock:
            if query:
                ext_category = ext_category_for(category)
            else:
                # Empty query = Prowlarr/RMAB "latest" (RSS) probe. Honour the
                # requested category when present; otherwise fall back to Movies
                # (cat=1) since extto.com renders no results table without one.
                ext_category = ext_category_for(category) if category else 1
            page = await self._browse(query, ext_category)
            # Fetch magnets eagerly only for real searches (a client is about to
            # grab a result): each magnet POST is paced (MIN_INTERVAL), so eager
            # magnets on an empty "latest"/RSS query would stall the feed past
            # client timeouts. RSS items are listed without a magnet and get one
            # on demand via search/detail when a release is actually grabbed.
            ordered = sorted(page.results, key=lambda t: t.seeders, reverse=True)
            eager = self.settings.eager_magnets if query else 0
            results: list[Torrent] = []
            for torrent in ordered:
                if len(results) < eager:
                    try:
                        torrent = torrent.with_magnet(await self._magnet(torrent.id))
                    except UpstreamError:
                        LOGGER.warning(
                            "magnet fetch failed for %s; listing without magnet",
                            torrent.id,
                        )
                    self._torrent_cache[torrent.id] = torrent
                else:
                    self._torrent_cache.setdefault(torrent.id, torrent)
                results.append(torrent)
            return results

    async def detail(self, torrent_id: str) -> Torrent | None:
        async with self._workflow_lock:
            cached = self._torrent_cache.get(torrent_id)
            if cached is not None:
                if cached.magnet is not None:
                    return cached
                try:
                    return cached.with_magnet(await self._magnet(torrent_id))
                except UpstreamError:
                    LOGGER.warning("magnet fetch failed for %s", torrent_id)
                    return cached
            # Cache miss: best-effort lookup by searching the site for the id.
            page = await self._browse(torrent_id)
            torrent = next((item for item in page.results if item.id == torrent_id), None)
            if torrent is None:
                return None
            try:
                torrent = torrent.with_magnet(await self._magnet(torrent.id))
            except UpstreamError:
                LOGGER.warning("magnet fetch failed for %s", torrent_id)
            self._torrent_cache[torrent.id] = torrent
            return torrent
