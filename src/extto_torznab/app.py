import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Protocol

from fastapi import FastAPI, HTTPException, Query, Response

from .config import Settings
from .models import Torrent
from .upstream import ExtToClient, UpstreamError
from .xml import render_caps, render_feed

LOGGER = logging.getLogger(__name__)


class Upstream(Protocol):
    last_success: datetime | None

    async def bootstrap(self) -> None: ...
    async def close(self) -> None: ...
    async def search(self, query: str, category: int | None = None) -> list[Torrent]: ...
    async def detail(self, torrent_id: str) -> Torrent | None: ...


def create_app(
    *,
    settings: Settings | None = None,
    api_key: str | None = None,
    upstream: Upstream | None = None,
) -> FastAPI:
    config = settings or Settings.from_env()
    expected_api_key = config.api_key if api_key is None else api_key
    extto = upstream or ExtToClient(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            try:
                await extto.bootstrap()
            except UpstreamError:
                LOGGER.exception("initial upstream health probe failed")
            yield
        finally:
            await extto.close()

    app = FastAPI(title="EXT Torrents Torznab", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        last_success = extto.last_success
        if last_success is None:
            raise HTTPException(status_code=503, detail="upstream has not succeeded yet")
        age = (datetime.now(UTC) - last_success).total_seconds()
        if age > config.health_max_age:
            raise HTTPException(status_code=503, detail="upstream success is stale")
        return {"status": "ok", "upstream_last_success": last_success.isoformat()}

    @app.get("/api")
    async def api(
        t: str = Query(...),
        apikey: str | None = Query(default=None),
        q: str | None = Query(default=None),
        cat: str | None = Query(default=None),
        torrent_id: str | None = Query(default=None, alias="id"),
    ) -> Response:
        if (
            not expected_api_key
            or apikey is None
            or not secrets.compare_digest(apikey, expected_api_key)
        ):
            raise HTTPException(status_code=401, detail="invalid API key")
        mode = t.casefold()
        if mode == "caps":
            return Response(render_caps(), media_type="application/xml")
        try:
            if mode == "search":
                category = _parse_category(cat)
                # An empty q is Prowlarr's "latest"/test probe; the upstream
                # client maps that to a default-category browse (see ExtToClient.search).
                torrents = await extto.search((q or "").strip(), category)
            elif mode == "detail":
                if not torrent_id:
                    raise HTTPException(status_code=400, detail="id is required for detail")
                torrent = await extto.detail(torrent_id)
                if torrent is None:
                    raise HTTPException(status_code=404, detail="torrent not found")
                torrents = [torrent]
            else:
                raise HTTPException(status_code=400, detail=f"unsupported t mode: {t}")
        except UpstreamError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return Response(
            render_feed(torrents, config.upstream_base),
            media_type="application/xml",
        )

    return app


def _parse_category(value: str | None) -> int | None:
    if not value:
        return None
    first = value.split(",", 1)[0].strip()
    try:
        return int(first)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="cat must contain numeric category IDs"
        ) from exc


app = create_app()
