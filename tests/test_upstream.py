from pathlib import Path
from urllib.parse import parse_qs

import httpx

from extto_torznab.config import Settings
from extto_torznab.upstream import ExtToClient, sign_magnet_request

FIXTURE = Path(__file__).parents[1] / "research/fixtures/browse_ubuntu_24_04.html"


async def test_verified_browse_and_magnet_protocol(monkeypatch) -> None:
    html = FIXTURE.read_text()
    requests: list[httpx.Request] = []
    browse_count = 0
    fixed_timestamp = 1_787_944_372

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal browse_count
        requests.append(request)
        if request.method == "GET":
            browse_count += 1
            assert request.url.path == "/browse/"
            assert request.headers.get("x-requested-with") is None
            assert request.url.params["q"] == "ubuntu 24.04"
            assert request.url.params["cat"] == "5"
            assert request.url.params["page"] == "1"
            assert request.url.params["page_size"] == "50"
            if browse_count == 1:
                return httpx.Response(
                    200,
                    text='<table class="search-table"></table>',
                    headers={"set-cookie": "PHPSESSID=discarded; Path=/"},
                )
            return httpx.Response(
                200,
                text=html,
                headers={"set-cookie": "PHPSESSID=same-session; Path=/"},
            )

        assert request.url.path == "/ajax/getSearchMagnet.php"
        assert request.headers["x-requested-with"] == "XMLHttpRequest"
        assert request.headers["referer"].startswith("https://extto.com/browse/?q=ubuntu+24.04&")
        assert "PHPSESSID=same-session" in request.headers["cookie"]
        form = parse_qs(request.content.decode(), keep_blank_values=True)
        torrent_id = form["torrent_id"][0]
        assert form == {
            "torrent_id": [torrent_id],
            "hash": [""],
            "name": [""],
            "timestamp": [str(fixed_timestamp)],
            "hmac": [
                sign_magnet_request(
                    torrent_id,
                    fixed_timestamp,
                    "31db34d4de129bc16fb0a000743a3efc",
                )
            ],
            "sessid": ["8b79a879634e6c600c384f044ae4ab43"],
        }
        return httpx.Response(
            200,
            json={
                "success": True,
                "url": f"magnet:?xt=urn:btih:{torrent_id}&dn=fixture",
            },
        )

    transport = httpx.MockTransport(handler)

    def new_client(_: ExtToClient) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://extto.com",
            transport=transport,
            headers={"User-Agent": "test"},
        )

    monkeypatch.setattr(ExtToClient, "_new_client", new_client)
    settings = Settings(
        api_key="test",
        min_interval=0,
        backoff_initial=0,
        backoff_cap=0,
    )
    client = ExtToClient(settings, wall_clock=lambda: fixed_timestamp)
    try:
        results = await client.search("ubuntu 24.04", 4000)
    finally:
        await client.close()

    assert browse_count == 2  # token-less first response caused a full session rotation
    assert len(results) == 12
    assert all(result.magnet and result.magnet.startswith("magnet:") for result in results)
    assert len(requests) == 14
