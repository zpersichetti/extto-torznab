# extto-torznab

A small FastAPI middleware that exposes the open `extto.com` mirror of EXT
Torrents as a Torznab indexer for Prowlarr. It fetches the full browse page,
keeps its PHP session and page tokens together, signs the site's magnet request,
and emits Newznab XML containing real magnet links.

The service deliberately serializes all upstream work. It waits at least three
seconds between upstream requests by default and exponentially backs off when
Cloudflare or an unparseable page is encountered. A 50-result search can
therefore take several minutes the first time; magnets are cached for 24 hours.

## Run with Docker Compose

```sh
export API_KEY='replace-with-a-long-random-value'
docker compose up --build -d
curl http://localhost:8123/healthz
```

Configuration:

| Variable | Default | Meaning |
|---|---:|---|
| `API_KEY` | required | Key required in every `/api` request |
| `UPSTREAM_BASE` | `https://extto.com` | EXT Torrents mirror base URL |
| `MIN_INTERVAL` | `3` | Minimum seconds between all upstream requests |
| `REQUEST_TIMEOUT` | `25` | Upstream HTTP timeout in seconds |
| `HEALTH_MAX_AGE` | `900` | Maximum age of a successful upstream response |
| `MAGNET_CACHE_TTL` | `86400` | Magnet cache lifetime in seconds |
| `EAGER_MAGNETS` | `10` | How many top-seeded results get magnets in search responses; the rest resolve on demand via `t=detail` |

Do not set `MIN_INTERVAL` below 3 against the public mirror. Burst traffic has
been observed to trigger Cloudflare blocks. Each magnet fetch is a separate paced
request, so search responses are limited to `EAGER_MAGNETS` eager magnets — the
remaining results are listed without an enclosure and get their magnet when
Prowlarr queries `t=detail` for a grab.

## Add it to Prowlarr

1. Open **Indexers**, choose **Add Indexer**, then select **Torznab**.
2. Set the URL to `http://host:8123/api`, replacing `host` with the Docker host.
3. Enter the same value used for `API_KEY` in Prowlarr's API key field.
4. Test and save the indexer. Categories are supplied by the Torznab caps response.

For a direct check:

```sh
curl --get 'http://localhost:8123/api' \
  --data-urlencode 't=search' \
  --data-urlencode 'q=ubuntu 24.04' \
  --data-urlencode "apikey=$API_KEY"
```

Supported modes are `t=caps`, `t=search&q=...` (with optional `cat`), and
`t=detail&id=...`. The key may be supplied as the standard `apikey` query
parameter. Missing or incorrect keys receive HTTP 401.

The top-level mapping was probed against each live `cat=1..8` browse page:

| extto.com ID and section | Newznab category |
|---|---:|
| 1 Movies | 2000 Movies |
| 2 TV | 5000 TV |
| 3 Music | 3000 Audio |
| 4 Games | 1000 Console |
| 5 Apps | 4000 PC |
| 6 Books | 7000 Books |
| 7 Anime | 5070 Anime |
| 8 Other | 8000 Other |

## Development

This project uses [uv](https://docs.astral.sh/uv/):

```sh
uv sync
uv run ruff check .
uv run pytest
```

Tests are fully offline. Parser coverage uses the verified page saved at
`research/fixtures/browse_ubuntu_24_04.html`; the signing test uses a fixed HMAC
vector derived from the verified protocol.

## Operational notes

- Browse GETs never carry `X-Requested-With`; doing so removes the required tokens.
- The `PHPSESSID`, `searchPageToken`, and CSRF token always stay in one client session.
- Failed or token-less browse responses rotate the entire session before retrying.
- `/healthz` returns 200 only when a valid upstream response succeeded recently.
- `UPSTREAM_BASE` can point at a replacement mirror if `extto.com` moves, but the
  replacement must implement the same verified browse and magnet protocol.
