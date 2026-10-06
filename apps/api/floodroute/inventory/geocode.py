"""Geocode place names with the public Nominatim service, within its usage policy.

Policy (https://operations.osmfoundation.org/policies/nominatim/, read 2026-10-05): at most 1 request
per second, a User-Agent that identifies the application, single thread, results cached on our side,
attribution (data from OpenStreetMap, ODbL). Small one-time batches only; bulk work belongs on our own
Nominatim or Photon instance. Never Ola Maps or Google here: their terms bar our use
(docs/research/02 section 1.2).

Confidence describes the point, not the query: high = a named point or short linear feature that
matches the query name; medium = a named place of up to about 4 km across; low = anything else
inside the city, or a name with several far-apart namesakes; none = no result inside the city box.
low and none need human review.
"""

import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from floodroute.inventory.match import dist_m, overlap, tokens

URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "FloodRoute-S5-inventory/0.1 (one-off research spike; named-place lookups, cached)"
MIN_GAP_S = 1.1  # policy ceiling is 1 request per second; keep a margin
NAMESAKE_M = 1000.0
STRUCTURE_WORDS = {
    "underpass",
    "underbridge",
    "railway",
    "vehicle",
    "flyover",
    "bridge",
    "junction",
}


def diag_m(bbox):
    """Diagonal in metres of a Nominatim boundingbox [south, north, west, east] (strings)."""
    s, n, w, e = (float(x) for x in bbox)
    return math.hypot((e - w) * 111320 * math.cos(math.radians((s + n) / 2)), (n - s) * 110540)


def _name(res):
    return res.get("name") or res.get("display_name", "").split(",")[0]


def confidence(results, query_name, box):
    """results: Nominatim rows for one query (best first, may be empty); box: (west, south, east, north).

    Returns (confidence, why). A second result with the same name more than NAMESAKE_M from the
    first means the name is ambiguous in this city, so the pick is capped at low.
    """
    res = results[0] if results else None
    if not res:
        return "none", ""
    lon, lat = float(res["lon"]), float(res["lat"])
    if not (box[0] <= lon <= box[2] and box[1] <= lat <= box[3]):
        return "none", ""
    want = tokens(query_name)
    for other in results[1:]:
        far = dist_m(lat, lon, [(float(other["lon"]), float(other["lat"]))]) > NAMESAKE_M
        if (
            far
            and overlap(want, tokens(_name(other))) >= 0.5
            and overlap(want, tokens(_name(res))) >= 0.5
        ):
            return "low", "ambiguous_namesakes"
    ext = diag_m(res["boundingbox"])
    ov = overlap(want, tokens(_name(res)))
    if int(res.get("place_rank", 0)) >= 26 and ext <= 1500 and ov >= 0.5:
        return "high", ""
    if ext <= 4000 and ov >= 0.5:
        return "medium", ""
    return "low", ""


def simplify(query):
    """Retry form of a failed query: generic structure words dropped from the part before the comma."""
    head, _, tail = query.partition(",")
    kept = [w for w in head.split() if w.lower() not in STRUCTURE_WORDS]
    if not kept or len(kept) == len(head.split()):
        return None
    return " ".join(kept) + ("," + tail if tail else "")


class Geocoder:
    """Cached, rate-limited Nominatim search. One instance, one thread."""

    def __init__(self, cache_dir, box, fetch=None, sleep=time.sleep, clock=time.monotonic):
        self.dir, self.box = Path(cache_dir), box
        self.dir.mkdir(parents=True, exist_ok=True)
        self._fetch, self._sleep, self._clock, self._last = fetch or self._http, sleep, clock, None
        self.requests = 0  # uncached requests actually sent

    def _http(self, url):
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    def _get(self, url):
        """HTTP 429 means the shared egress IP is over the limit: back off 20, 40, 80 s, then give up.
        Any other HTTP error propagates at once. Results already fetched are cached, so a rerun resumes."""
        for pause in (20, 40, 80, None):
            try:
                return self._fetch(url)
            except urllib.error.HTTPError as e:
                if e.code != 429 or pause is None:
                    raise
                self._sleep(pause)

    def search(self, query):
        """Up to 3 results inside the city box (Nominatim 'bounded' viewbox), best first; [] if none."""
        west, south, east, north = self.box
        qs = urllib.parse.urlencode(
            {
                "q": query,
                "format": "jsonv2",
                "limit": 3,
                "countrycodes": "in",
                "bounded": 1,
                "viewbox": f"{west},{north},{east},{south}",
            }
        )
        url = f"{URL}?{qs}"
        f = self.dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")
        if f.exists():
            rows = json.loads(f.read_text())["response"]
        else:
            if self._last is not None and (wait := MIN_GAP_S - (self._clock() - self._last)) > 0:
                self._sleep(wait)
            rows = self._get(url)
            self._last = self._clock()
            self.requests += 1
            f.write_text(
                json.dumps(
                    {
                        "query": query,
                        "url": url,
                        "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "response": rows,
                    }
                )
            )
        return rows
