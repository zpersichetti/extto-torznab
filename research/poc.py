#!/usr/bin/env python3
"""
ext.to (extto.com mirror) search + magnet PoC — VERIFIED 2026-08-28.

Full pipeline proven live: browse-page search, table parsing, and the site's
HMAC-signed magnet endpoint (SHA256 of "id|ts|searchPageToken").

Usage:
    python3 poc.py search "ubuntu 24.04"          # list results (no magnet fetch)
    python3 poc.py magnet <torrent_id>            # get magnet for a known id
    python3 poc.py search "ubuntu 24.04" --magnet # search then fetch first N magnets

Notes:
  - ext.to / ext2.to are Cloudflare-Turnstile-walled; extto.com is open.
  - Tokens (PHPSESSID, searchPageToken, csrf-token) are session-bound:
    they must come from the SAME page fetch that the POST reuses.
  - Do NOT send X-Requested-With on the browse GET — the server then returns
    an 85KB AJAX fragment without tokens. It IS required on the magnet POST.
  - Throttle: bursts of requests trigger CF 403s; keep >=3s between calls.
"""
import argparse
import hashlib
import http.cookiejar
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://extto.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.4 Safari/605.1.15")


class ExttoSession:
    """One PHPSESSID session with its page tokens."""

    def __init__(self):
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj))
        self._opener.addheaders = [("User-Agent", UA)]
        self.tokens = None  # (searchPageToken, csrf)

    def _get(self, url, xhr=False):
        req = urllib.request.Request(url)
        if xhr:
            req.add_header("X-Requested-With", "XMLHttpRequest")
        return self._opener.open(req, timeout=25).read().decode("utf-8", "ignore")

    def fetch_browse(self, query, cat=None, page=1):
        """GET a browse page and extract tokens. Returns parsed rows."""
        params = {"q": query, "page": page, "page_size": 50}
        if cat:
            params["cat"] = cat
        url = f"{BASE}/browse/?{urllib.parse.urlencode(params)}"
        body = None
        for attempt in range(3):
            body = self._get(url)
            tok = re.search(r"searchPageToken\s*=\s*'([^']+)'", body)
            csrf = re.search(r'<meta[^>]*csrf-token[^>]*content="([^"]+)"', body)
            if tok and csrf:
                self.tokens = (tok.group(1), csrf.group(1))
                break
            print(f"  ...unparseable response ({len(body)}B), retry in 8s")
            time.sleep(8)
        if not self.tokens:
            raise RuntimeError("could not obtain a parseable browse page "
                               "(rate-limited by Cloudflare?)")
        return parse_results(body)

    def get_magnet(self, torrent_id):
        """POST the signed endpoint. Returns magnet URL string."""
        if not self.tokens:
            raise RuntimeError("no session tokens; call fetch_browse first")
        page_token, csrf = self.tokens
        ts = int(time.time())
        hmac = hashlib.sha256(f"{torrent_id}|{ts}|{page_token}".encode()).hexdigest()
        data = urllib.parse.urlencode({
            "torrent_id": torrent_id, "hash": "", "name": "",
            "timestamp": ts, "hmac": hmac, "sessid": csrf,
        }).encode()
        req = urllib.request.Request(f"{BASE}/ajax/getSearchMagnet.php",
                                     data=data, method="POST")
        req.add_header("X-Requested-With", "XMLHttpRequest")
        req.add_header("Referer", f"{BASE}/browse/")
        resp = self._opener.open(req, timeout=25)
        import json
        return json.loads(resp.read().decode("utf-8", "ignore"))


def parse_results(body):
    """Parse table.search-table rows -> list of dicts."""
    rows = re.findall(r"<tr>(.*?)</tr>", body, re.S)
    out = []
    for row in rows:
        if "torrent-title-link" not in row:
            continue
        m = re.search(r'href="/([^"/]+?)-(\d+)/" class="torrent-title-link"', row)
        if not m:
            continue
        slug, tid = m.group(1), m.group(2)
        title = re.sub(r"<[^>]+>", "", re.search(
            r'class="torrent-title-link"[^>]*>(.*?)</a>', row, re.S).group(1)).strip()
        def field(name):
            mm = re.search(rf"<span class=\"add-block\">{name}</span>\s*<span[^>]*>([^<]+)</span>", row)
            return mm.group(1).strip() if mm else ""
        out.append({
            "id": tid, "slug": slug, "title": title,
            "size": field("Size"), "files": field("Files"),
            "age": field("Age"), "seeds": field("Seeds"), "leechs": field("Leechs"),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="ext.to PoC (via extto.com)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--magnet", type=int, metavar="N", default=0,
                          help="fetch magnets for first N results")
    p_magnet = sub.add_parser("magnet")
    p_magnet.add_argument("torrent_id")
    args = ap.parse_args()

    s = ExttoSession()
    if args.cmd == "magnet":
        s.fetch_browse("test")  # bootstrap session/tokens
        print(s.get_magnet(args.torrent_id).get("url"))
        return

    results = s.fetch_browse(args.query)
    print(f"{len(results)} results for '{args.query}':\n")
    for i, r in enumerate(results, 1):
        print(f"[{i}] {r['title']}")
        print(f"    id={r['id']}  size={r['size']}  seeds={r['seeds']}  "
              f"leechs={r['leechs']}  files={r['files']}  age={r['age']}")
    if args.magnet:
        print()
        for r in results[: args.magnet]:
            time.sleep(3)  # throttle
            try:
                mag = s.get_magnet(r["id"])
                print(f"id {r['id']}: {mag.get('url', mag)[:110]}...")
            except Exception as e:
                print(f"id {r['id']}: ERROR {e}")


if __name__ == "__main__":
    sys.exit(main())
