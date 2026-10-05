"""Runner and HTTP client: health rows, exit codes, the one-request-per-second rule, retries, caps."""

import gzip

import httpx
import pytest
from ingest_testkit import NOW, FakeConn

from floodroute.ingest import __main__ as cli
from floodroute.ingest import common
from floodroute.ingest.common import (
    MAX_WAIT,
    FetchError,
    Http,
    HttpStatusError,
    Outcome,
    TooLarge,
)

URL = "https://a.example/x"


class Clock:
    """A fake monotonic clock that only moves when something sleeps or the test advances it."""

    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


def make(handler, clock, hosts=("a.example",), **kw):
    transport = httpx.MockTransport(handler)
    return Http(hosts, transport=transport, sleep=clock.sleep, clock=clock, **kw)


def seen_at(clock, stamps, response=None):
    def handler(request):
        stamps.append((clock.t, request.url.host))
        return response or httpx.Response(200, content=b"ok")

    return handler


# ---------------------------------------------------------------- rate limit

def test_requests_to_one_host_are_at_least_a_second_apart():
    clock, stamps = Clock(), []
    http = make(seen_at(clock, stamps), clock)
    for _ in range(4):
        assert http.get(URL, 100) == b"ok"
    times = [t for t, _ in stamps]
    assert times == [0.0, 1.0, 2.0, 3.0] and clock.sleeps == [1.0, 1.0, 1.0]


def test_a_slow_response_already_counts_towards_the_gap():
    clock, stamps = Clock(), []

    def handler(request):
        stamps.append(clock.t)
        clock.t += 0.4
        return httpx.Response(200, content=b"ok")

    http = make(handler, clock)
    http.get(URL, 100)
    http.get(URL, 100)
    assert stamps == [0.0, 1.0] and clock.sleeps == [pytest.approx(0.6)]


def test_hosts_are_paced_independently():
    clock, stamps = Clock(), []
    http = make(seen_at(clock, stamps), clock, hosts=("a.example", "b.example"))
    http.get("https://a.example/1", 100)
    http.get("https://b.example/1", 100)  # another host: no wait
    http.get("https://a.example/2", 100)
    assert stamps == [(0.0, "a.example"), (0.0, "b.example"), (1.0, "a.example")]


def test_retries_are_paced_too():
    clock, stamps = Clock(), []
    answers = iter([httpx.Response(503), httpx.Response(200, content=b"ok")])
    http = make(lambda r: (stamps.append(clock.t), next(answers))[1], clock, backoff=0.1)
    assert http.get(URL, 100) == b"ok"
    assert stamps == [0.0, 1.0]  # backoff 0.1 s is shorter than the one second rule


# ---------------------------------------------------------------- retries

def test_503_is_retried_with_exponential_backoff():
    clock, stamps = Clock(), []
    answers = iter([httpx.Response(503), httpx.Response(502), httpx.Response(200, content=b"ok")])
    http = make(lambda r: (stamps.append(clock.t), next(answers))[1], clock)
    assert http.get(URL, 100) == b"ok"
    assert clock.sleeps == [2.0, 4.0] and [t for t in stamps] == [0.0, 2.0, 6.0]


def test_retries_are_bounded():
    clock, stamps = Clock(), []
    http = make(seen_at(clock, stamps, httpx.Response(503)), clock)
    with pytest.raises(HttpStatusError) as err:
        http.get(URL, 100)
    assert err.value.status == 503 and len(stamps) == 3  # one try and two retries
    http = make(seen_at(clock, stamps := [], httpx.Response(503)), clock, retries=0)
    with pytest.raises(HttpStatusError):
        http.get(URL, 100)
    assert len(stamps) == 1


def test_retry_after_is_honoured_and_capped():
    for header, expected in (("5", 5.0), ("99999", MAX_WAIT)):
        clock = Clock()
        answers = iter([httpx.Response(429, headers={"retry-after": header}),
                        httpx.Response(200, content=b"ok")])
        http = make(lambda r, a=answers: next(a), clock)
        assert http.get(URL, 100) == b"ok"
        assert clock.sleeps == [expected]


def test_network_errors_are_retried_then_reported():
    clock = Clock()
    calls = []

    def flaky(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("Connection reset by peer")
        return httpx.Response(200, content=b"ok")

    assert make(flaky, clock).get(URL, 100) == b"ok"

    def down(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(FetchError, match="ReadTimeout"):
        make(down, Clock()).get(URL, 100)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 301, 302, 307])
def test_client_errors_and_redirects_are_not_retried_or_followed(status):
    clock, stamps = Clock(), []
    answer = httpx.Response(status, headers={"location": "https://evil.example/"})
    with pytest.raises(HttpStatusError) as err:
        make(seen_at(clock, stamps, answer), clock).get(URL, 100)
    assert err.value.status == status and len(stamps) == 1


# ---------------------------------------------------------------- caps and allow-list

def test_declared_oversize_body_is_refused_without_a_retry():
    clock, stamps = Clock(), []
    http = make(seen_at(clock, stamps, httpx.Response(200, content=b"x" * 200)), clock)
    with pytest.raises(TooLarge):
        http.get(URL, 100)
    assert len(stamps) == 1
    assert http.get(URL, 200) == b"x" * 200  # exactly at the cap is fine


def test_undeclared_oversize_body_is_cut_off_while_streaming():
    def chunks():
        for _ in range(1000):
            yield b"x" * 100

    with pytest.raises(TooLarge):
        make(lambda r: httpx.Response(200, content=chunks()), Clock()).get(URL, 1000)


def test_gzip_bomb_is_counted_after_decompression():
    bomb = gzip.compress(b"\0" * 5_000_000)
    assert len(bomb) < 10_000
    answer = httpx.Response(200, headers={"content-encoding": "gzip"}, content=bomb)
    with pytest.raises(TooLarge):
        make(lambda r: answer, Clock()).get(URL, 100_000)


def test_a_body_that_never_finishes_hits_the_deadline():
    clock = Clock()

    def trickle():
        yield b"a"
        clock.t += 100
        yield b"b"

    with pytest.raises(FetchError, match="within 60s"):
        make(lambda r: httpx.Response(200, content=trickle()), clock).get(URL, 1000)


@pytest.mark.parametrize("url", [
    "http://a.example/x", "https://evil.example/x", "https://a.example.evil.example/x",
    "ftp://a.example/x", "file:///etc/passwd", "https://169.254.169.254/latest", "//a.example/x",
])
def test_only_https_and_listed_hosts_are_fetched(url):
    def never(request):
        raise AssertionError("request should not have been sent")

    with pytest.raises(FetchError, match="refusing"):
        make(never, Clock()).get(url, 100)


def test_user_agent_identifies_the_client_and_cannot_be_split(monkeypatch):
    sent = []

    def handler(request):
        sent.append(request.headers["user-agent"])
        return httpx.Response(200)

    monkeypatch.delenv("FLOODROUTE_CONTACT", raising=False)
    make(handler, Clock()).get(URL, 100)
    monkeypatch.setenv("FLOODROUTE_CONTACT", "ops@example.org\r\nX-Evil: 1")
    make(handler, Clock()).get(URL, 100)
    assert sent[0] == "FloodRouteIngest/0.1 (+https://github.com/Krishpotanwar/flood-route)"
    assert sent[1] == "FloodRouteIngest/0.1 (+ops@example.org X-Evil: 1)" and "\n" not in sent[1]


def test_india_box_catches_swapped_coordinates():
    assert common.in_india(12.97, 77.59) and common.in_india(8.0, 72.0)
    assert not common.in_india(77.59, 12.97)  # lon,lat order
    assert not common.in_india(float("nan"), 77.0) and not common.in_india(12.0, float("inf"))


# ---------------------------------------------------------------- runner

def clock_at(*times):
    stamps = iter(times)
    return lambda: next(stamps)


def test_a_clean_run_writes_health_and_releases_the_lock(capsys):
    conn = FakeConn()
    code = common.run(conn, "x", lambda c: Outcome({"n": 3}, 42), clock=lambda: NOW)
    assert code == 0
    assert conn.health["x"] == {"last_ok": NOW, "last_error": None, "lag_s": 42}
    statements = [s for s, _ in conn.calls]
    assert statements[0].startswith("select pg_try_advisory_lock")
    assert statements[-1].startswith("select pg_advisory_unlock")
    assert '"n": 3' in capsys.readouterr().out


def test_warnings_keep_last_ok_moving_and_say_what_was_refused():
    conn = FakeConn()
    assert common.run(conn, "x", lambda c: Outcome({}, 5, "2 items\nrefused"), clock=lambda: NOW) == 0
    assert conn.health["x"] == {"last_ok": NOW, "last_error": "warning: 2 items refused", "lag_s": 5}


def test_a_failed_run_exits_one_keeps_last_ok_and_unknowns_the_lag(capsys):
    conn = FakeConn()
    first, second = NOW, NOW.replace(hour=21)
    assert common.run(conn, "x", lambda c: Outcome({}, 42), clock=lambda: first) == 0

    def boom(c):
        raise FetchError("ConnectError: Connection reset by peer")

    assert common.run(conn, "x", boom, clock=lambda: second) == 1
    health = conn.health["x"]
    assert health["last_ok"] == first  # the true age of the feed stays readable
    assert health["lag_s"] is None  # unknown is not the previous number
    assert health["last_error"] == (
        "2026-10-05T21:30:00Z failed: FetchError: ConnectError: Connection reset by peer")
    assert "Connection reset" in capsys.readouterr().err

    assert common.run(conn, "x", lambda c: Outcome({}, 7), clock=lambda: second) == 0
    assert conn.health["x"] == {"last_ok": second, "last_error": None, "lag_s": 7}


def test_the_first_ever_run_failing_still_leaves_a_row():
    conn = FakeConn()
    assert common.run(conn, "x", lambda c: 1 / 0, clock=lambda: NOW) == 1
    assert conn.health["x"]["last_ok"] is None and "ZeroDivisionError" in conn.health["x"]["last_error"]


def test_error_text_is_one_short_line():
    conn = FakeConn()

    def boom(c):
        raise ValueError("line one\n" + "x" * 2000)

    common.run(conn, "x", boom, clock=lambda: NOW)
    text = conn.health["x"]["last_error"]
    assert "\n" not in text and len(text) < 600


def test_if_the_failure_cannot_be_recorded_the_exit_code_is_still_one(capsys):
    conn = FakeConn()
    conn.fail_on = "insert into source_health"
    assert common.run(conn, "x", lambda c: 1 / 0, clock=lambda: NOW) == 1
    assert "could not record the failure" in capsys.readouterr().err


def test_a_success_that_cannot_be_recorded_is_a_failed_run():
    conn = FakeConn()
    conn.fail_on = "insert into source_health"
    assert common.run(conn, "x", lambda c: Outcome({}, 1), clock=lambda: NOW) == 1


def test_a_second_run_of_the_same_adapter_does_not_start():
    conn = FakeConn()
    conn.lock_free = False
    called = []
    assert common.run(conn, "x", lambda c: called.append(1) or Outcome({}, 1)) == 0
    assert called == [] and conn.health == {}
    assert not any(s.startswith("select pg_advisory_unlock") for s, _ in conn.calls)


def test_other_adapters_use_other_locks():
    a, b = FakeConn(), FakeConn()
    common.run(a, "sachet", lambda c: Outcome({}, 1), clock=lambda: NOW)
    common.run(b, "metno", lambda c: Outcome({}, 1), clock=lambda: NOW)
    assert a.calls[0][1] != b.calls[0][1]


def test_a_connection_that_is_not_autocommit_is_refused():
    conn = FakeConn()
    conn.autocommit = False
    with pytest.raises(ValueError, match="autocommit"):
        common.run(conn, "x", lambda c: Outcome({}, 1))


# ---------------------------------------------------------------- command line

def test_cli_usage_errors_exit_two(capsys):
    with pytest.raises(SystemExit) as err:
        cli.main(["nope"])
    assert err.value.code == 2
    with pytest.raises(SystemExit) as err:
        cli.main([])
    assert err.value.code == 2


def test_cli_without_a_database_exits_one(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert cli.main(["sachet", "--once"]) == 1
    assert "DATABASE_URL is not set" in capsys.readouterr().err
