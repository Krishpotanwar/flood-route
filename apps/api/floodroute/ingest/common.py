"""Shared ingestion plumbing: a polite HTTP client and a runner that reports its own health.

TRD section 5 contract: an adapter is one CLI command, idempotent (primary-key upserts), writes
source_health and exits non-zero on failure. `run()` enforces the last two and takes care of the
first overlap case (two cron runs of one adapter) with a Postgres advisory lock.

source_health as written by run(), for readers (scoring, console):
  last_ok     time of the last run that finished its work. A run that finished with warnings counts.
  last_error  NULL after a clean run. "warning: ..." after a run that finished but refused some
              input or is catching up. "<UTC time> failed: ..." after a failed run (last_ok is then
              left alone, so now() - last_ok is the true age of the feed).
  lag_s       age in seconds of the source's own newest data when last_ok was written. NULL while the
              last run failed: unknown must be read as stale, never as the previous number.

HTTP: https only, an explicit host allow-list, no redirects, at most one request per second per host
(`min_interval`), bounded retries with exponential backoff on 408/429/5xx and network errors, a body
cap counted after decompression and a wall-clock deadline per request. Retry-After is honoured up to
MAX_WAIT seconds. The pacing is per process; the advisory lock keeps one process per adapter.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import sys
import time
import zlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, NamedTuple
from urllib.parse import urlsplit

import httpx

# Generous box around India, its seas and islands. Its job is to catch swapped lat,lon and garbage.
INDIA_LAT = (0.0, 40.0)
INDIA_LON = (60.0, 100.0)
RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})
MAX_WAIT = 60.0


class Rejected(ValueError):
    """Untrusted content we refuse to ingest (hostile, malformed, out of spec). Never retried."""


class TooLarge(Rejected):
    """Body over the cap."""


class FetchError(Exception):
    """Network or HTTP failure after bounded retries. The run fails; the next cron run retries."""


class HttpStatusError(FetchError):
    def __init__(self, status: int, url: str, retry_after: float | None = None):
        super().__init__(f"HTTP {status} from {urlsplit(url).hostname}")
        self.status = status
        self.retry_after = retry_after


class IngestError(Exception):
    """The run as a whole failed (as opposed to one item being rejected)."""


class Outcome(NamedTuple):
    summary: dict
    lag_s: int | None
    warn: str | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)


def in_india(lat: float, lon: float) -> bool:
    ok = math.isfinite(lat) and math.isfinite(lon)
    return ok and INDIA_LAT[0] <= lat <= INDIA_LAT[1] and INDIA_LON[0] <= lon <= INDIA_LON[1]


def user_agent() -> str:
    # api.met.no bans clients without a way to contact them, so production sets FLOODROUTE_CONTACT.
    contact = " ".join(os.environ.get("FLOODROUTE_CONTACT", "").split())
    return f"FloodRouteIngest/0.1 (+{contact or 'https://github.com/Krishpotanwar/flood-route'})"


class Http:
    def __init__(
        self,
        allowed_hosts,
        *,
        min_interval: float = 1.0,
        timeout: float = 20.0,
        deadline: float = 60.0,
        retries: int = 2,
        backoff: float = 2.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.allowed_hosts = frozenset(allowed_hosts)
        self.min_interval, self.deadline = min_interval, deadline
        self.retries, self.backoff = retries, backoff
        self._sleep, self._clock = sleep, clock
        self._last: dict[str, float] = {}
        self._client = httpx.Client(
            headers={"User-Agent": user_agent()},
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def get(self, url: str, max_bytes: int) -> bytes:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in self.allowed_hosts:
            raise FetchError(f"refusing to fetch {parts.scheme}://{parts.hostname}")
        for attempt in range(self.retries + 1):
            self._pace(parts.hostname)
            wait = None
            try:
                return self._once(url, max_bytes)
            except HttpStatusError as e:
                if e.status not in RETRY_STATUS or attempt == self.retries:
                    raise
                wait = e.retry_after
            except httpx.RequestError as e:
                if attempt == self.retries:
                    raise FetchError(f"{type(e).__name__}: {e}") from e
            self._sleep(min(self.backoff * 2**attempt if wait is None else wait, MAX_WAIT))

    def _pace(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            delay = self.min_interval - (self._clock() - last)
            if delay > 0:
                self._sleep(delay)
        self._last[host] = self._clock()

    def _once(self, url: str, max_bytes: int) -> bytes:
        started = self._clock()
        with self._client.stream("GET", url) as r:
            if r.status_code != 200:
                retry_after = r.headers.get("retry-after", "")
                raise HttpStatusError(
                    r.status_code, url, float(retry_after) if retry_after.isdigit() else None
                )
            declared = r.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > max_bytes:
                raise TooLarge(f"content-length {declared} over {max_bytes}")
            body = bytearray()
            for chunk in r.iter_bytes():  # decoded bytes, so a gzip bomb is counted too
                body += chunk
                if len(body) > max_bytes:
                    raise TooLarge(f"body over {max_bytes} bytes")
                if self._clock() - started > self.deadline:
                    raise FetchError(f"no complete body within {self.deadline:.0f}s")
        return bytes(body)


OK_SQL = """
insert into source_health (source, last_ok, last_error, lag_s) values (%s, %s, %s, %s)
on conflict (source) do update
set last_ok = excluded.last_ok, last_error = excluded.last_error, lag_s = excluded.lag_s
"""
FAIL_SQL = """
insert into source_health (source, last_error) values (%s, %s)
on conflict (source) do update set last_error = excluded.last_error, lag_s = null
"""


def _clip(text: str) -> str:
    return " ".join(text.split())[:500]


def _say(payload: dict, stream=None) -> None:
    print(json.dumps(payload, default=str), file=stream or sys.stdout, flush=True)


def run(
    conn: Any,
    source: str,
    work: Callable[[Any], Outcome],
    *,
    clock: Callable[[], datetime] = utcnow,
) -> int:
    """Run one pass of an adapter and record it in source_health. Returns the process exit code.

    `conn` is a psycopg connection in autocommit mode. `work(conn)` does its own writes in small
    transactions (so progress survives a later failure) and returns an Outcome. Any exception
    is a failed run. Another live run of the same adapter makes this one a no-op.
    """
    if not conn.autocommit:
        raise ValueError("ingest needs an autocommit connection")
    key = zlib.crc32(f"floodroute.ingest.{source}".encode())
    if not conn.execute("select pg_try_advisory_lock(%s)", (key,)).fetchone()[0]:
        _say({"source": source, "ok": True, "skipped": "another run holds the lock"})
        return 0
    try:
        out = work(conn)
        warn = f"warning: {_clip(out.warn)}" if out.warn else None
        with conn.transaction():
            conn.execute(OK_SQL, (source, clock(), warn, out.lag_s))
        _say({"source": source, "ok": True, "lag_s": out.lag_s, "warn": warn, **out.summary})
        return 0
    except Exception as e:  # noqa: BLE001 - every failure must reach source_health
        err = f"{clock():%Y-%m-%dT%H:%M:%SZ} failed: {type(e).__name__}: {_clip(str(e))}"
        _say({"source": source, "ok": False, "error": err}, sys.stderr)
        try:
            with conn.transaction():
                conn.execute(FAIL_SQL, (source, err))
        except Exception as e2:  # noqa: BLE001 - the database itself may be what failed
            print(f"could not record the failure: {e2!r}", file=sys.stderr)
        return 1
    finally:
        with contextlib.suppress(Exception):
            conn.execute("select pg_advisory_unlock(%s)", (key,))
