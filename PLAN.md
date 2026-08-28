# ext.to → Prowlarr Integration Plan

**Status:** Research complete, PoC verified end-to-end (2026-08-28)
**Goal:** Add ext.to (EXT Torrents) as a searchable indexer in Prowlarr.

---

## 1. Executive Summary

ext.to itself is **not directly scrapable** — it sits behind a Cloudflare Turnstile
("Verify you are human") wall that blocks even headless Chromium. However, the
**`extto.com` mirror is wide open** (plain HTTP, no challenge) and serves identical
content. The plan is a small **middleware container** that:

1. Exposes a **Torznab API** (`?t=search&q=...`) to Prowlarr,
2. Translates queries to `extto.com` browse pages,
3. Parses the results table,
4. Fetches real **magnet links** by replicating the site's client-side HMAC signing,
5. Returns Newznab XML to Prowlarr.

**PoC status: full pipeline verified live** — search returns results, and the signed
magnet endpoint returns `magnet:?xt=urn:btih:<HASH>&dn=...&tr=...` with trackers.
See `research/poc.py`.

---

## 2. Recon Findings (verified)

### 2.1 Access surface

| Domain | Status | Notes |
|---|---|---|
| `ext.to` (origin) | 🔒 CF Turnstile wall | "Verify you are human" checkbox; headless Chromium stopped too |
| `ext2.to` (mirror) | 🔒 CF "Just a moment" | 403 for curl |
| **`extto.com` (mirror)** | ✅ **Open** | HTTP 200, full content, no challenge |

`extto.com` is the same site (title: "EXT Torrents - All torrents to All"). The
middleware targets it exclusively; the origin is only relevant if the mirror dies
(see Risks).

### 2.2 Rate limiting / anti-bot quirks (all observed live)

- **Bursts trigger CF 403s.** ~10 rapid requests → "Just a moment" or unparseable
  variants. Recovers after ~20s cooldown. → Middleware MUST throttle (e.g. min
  2–4s between requests) and retry with backoff.
- **`X-Requested-With: XMLHttpRequest` on the browse GET returns an 85KB AJAX
  fragment** (results but NO tokens). Without it you get the 754KB full page with
  tokens. → Never send that header on browse GETs; it's fine on the magnet POST.
- **Tokens are session-bound**: `PHPSESSID` cookie, `searchPageToken`, and the
  `csrf-token` meta must all come from the SAME page fetch.

### 2.3 Search protocol (verified)

```
GET https://extto.com/browse/?q=<query>&cat=<N>&sort=seeds&order=desc&page=N&page_size=50
```

- Results live in `table.search-table` (12 rows for test query; 50 default per page).
- Row fields (each `<td>`): name+slug, size, files, age, seeds, leechs, source badge.
  - Age cell: `<span title="09 August 2025">1 year ago</span>` — the `title` attr
    holds the exact date; use it for Newznab `pubDate` (fallback: parse "X ago").
- Torrent link: `href="/<slug>-<id>/"` with `class="torrent-title-link"`.
- Magnet button: `<a class="search-magnet-btn" data-id="<id>">` (hash/name attrs
  absent on browse page — sent empty).
- Page shell also embeds (inline script): `window.searchPageToken = '<32 hex>'`
  and `<meta name="csrf-token" content="<32 hex>">`.

### 2.4 Magnet protocol (verified end-to-end)

```
POST https://extto.com/ajax/getSearchMagnet.php
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest
Referer: <the browse URL>
Cookie: PHPSESSID=<from browse fetch>

torrent_id=<id>
hash=
name=
timestamp=<unix seconds>
hmac=SHA256("<torrent_id>|<timestamp>|<searchPageToken>")
sessid=<csrf-token meta>
```

Response:
```json
{"success":true,"downloads":933,"url":"magnet:?xt=urn:btih:C9BC96D2...&dn=...&tr=udp://tracker.opentrackr.org:1337&tr=..."}
```

Detail pages use a sibling endpoint `POST /ajax/getTorrentMagnet.php` with
`action: get_magnet|get_hash` and `window.pageToken` instead — not needed for
browse/search flow, but worth supporting for `t=detail` later.

### 2.5 Categories

Top-level sections: Movies (`/movies/`), TV (`/tv-series/`, `/tv/`), Music, Games,
Applications, Books, Anime. Browse `cat=` ids 1–8 exist (plus sub_cats like 12, 48).
**TODO during build:** map each `cat=N` to its name (fetch `/browse/?cat=N`, read
breadcrumb) and to Newznab categories (Movie=2000, TV=5000, Audio=3000, PC=4000,
Books=7000, Console=1000, Anime→TV/Other). Expose via `?t=caps`.

---

## 3. Architecture

```
Prowlarr ──(Torznab XML)──▶ extto-prowlarr middleware (FastAPI, :8123)
                               │
                               ├─ SessionManager  (PHPSESSID + token cache, refresh)
                               ├─ Throttle        (min-interval + retry/backoff)
                               ├─ Searcher        (browse page fetch + table parse)
                               ├─ MagnetFetcher   (HMAC sign + POST + magnet cache)
                               └─ XML renderer    (Newznab 1.0 output)
                               │
                               ▼
                          extto.com (mirror)
```

### 3.1 Components

- **Torznab endpoint** `GET /api?t=search&q=<query>&cat=<newznab>&apikey=...`
  (also `t=caps`, `t=search&mode=rss`-style latest, `t=detail&id=<id>`).
  API key via env `API_KEY`; plain `/api` passthrough optional (Prowlarr sends key).
- **Searcher**: GET browse page (no XHR header) → parse `table.search-table` rows
  (BeautifulSoup/lxml). Map `cat` filter → ext.to `cat=`/`sub_cat=` if possible,
  else post-filter.
- **MagnetFetcher**: lazy per-result (fetch on demand, cache by torrent id, TTL
  ~24h). Replicate HMAC exactly; keep one session per refresh cycle.
- **SessionManager**: on startup and after any 403/unparseable response, fetch a
  fresh browse page to rotate PHPSESSID + tokens. Serialize access (one in-flight
  session refresh).
- **Throttle**: min 3s between upstream requests; exponential backoff on CF 403
  (start 10s, cap 120s). Burst-safe.
- **XML renderer**: Newznab 1.0 (RSS items with `guid`, `title`, `link` =
  detail page, `enclosure url=<magnet>` or `magnet` in description, `size`,
  `seeders`/`peers` in torznab:attr, `category`). Must pass Prowlarr validation.

### 3.2 Container

- `Dockerfile`: python:3.12-slim, FastAPI + uvicorn, beautifulsoup4, httpx
  (or requests), no root, healthcheck hitting `/healthz`.
- `docker-compose.yml`: service with env `API_KEY`, `UPSTREAM_BASE=https://extto.com`,
  `MIN_INTERVAL=3`, published port `8123:8123`, `restart: unless-stopped`.
- Prowlarr side (no plugin needed): Settings → Indexers → Add → **Torznab**,
  URL `http://<host>:8123/api?apikey=<API_KEY>` (or `/api` + key field),
  category set from caps, no auth (LAN) or basic auth as preferred.

### 3.3 Testing (TDD per repo convention)

- Unit: HMAC signing vector (replay the exact PoC values), table parser against
  saved fixtures, XML renderer schema.
- Integration (offline): fixtures from saved pages.
- Optional live smoke test (tagged, run manually): search + magnet for a real query.
- Verified merge: agent commits to `feature/` branch, opens PR, CI/lint gate.

---

## 4. Build Steps (for the coding agent)

1. Read this plan + `research/poc.py` (the verified ground truth).
2. Scaffold FastAPI project (pyproject/uv, src layout) with TDD.
3. Implement SessionManager → Searcher → MagnetFetcher → Torznab endpoints
   (caps + search first; detail optional).
4. Map `cat=` 1–8 → names + Newznab categories; hardcode from live probe.
5. Dockerfile + compose + healthcheck; README with Prowlarr setup steps.
6. Commit to `feature/extto-torznab`, push, open PR to `main`.

## 5. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| CF starts challenging `extto.com` | Throttle discipline; session rotation; monitor via healthcheck; fall back to `ext2.to`/origin behind FlareSolverr as stretch |
| Tokens/HMAC scheme change | Single point of failure isolated in `MagnetFetcher`; golden test vectors; alert on 3+ failures |
| Rate-limit bans | Conservative `MIN_INTERVAL`; never parallel upstream requests; exponential backoff |
| Site ToS | Personal-use indexer, low query volume; respect robots by pacing |
| Mirror death | `UPSTREAM_BASE` env override; README documents fallback domains |

## 6. Open Questions / Next Steps

- [ ] Map cat ids 1–8 → section names (build step)
- [ ] Probe `.torrent` file download (detail-page `download_type=file`) for enclosure fallback
- [ ] Decide `t=detail` support (Prowlarr uses it for manual downloads)
- [ ] Confirm Prowlarr Torznab custom-indexer fields on current version
