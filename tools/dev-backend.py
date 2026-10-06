"""Reproducible local API smoke check; stdlib only. --report writes a synthetic unmatched report."""
# ruff: noqa: N999

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone


def request(base, path, body=None):
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--require-route", action="store_true")
    parser.add_argument("--report", action="store_true", help="write a synthetic pending test report")
    args = parser.parse_args()

    code, raw = request(args.url, "/app/?live=1")
    assert code == 200 and b'<div id="root">' in raw, ("citizen frontend", code)
    code, raw = request(args.url, "/v1/health")
    health = json.loads(raw)
    assert code == 200 and health["database"] == "connected", ("health", code, health)
    print("PASS frontend and database; source status:", json.dumps(health["sources"]))

    code, raw = request(args.url, "/v1/feed/snapshot/closures?city=bengaluru&vclass=car")
    snapshot = json.loads(raw)
    assert code == 200 and snapshot["type"] == "FeatureCollection", ("snapshot", code, snapshot)
    assert snapshot["vclass"] == "car" and isinstance(snapshot["stale"], bool)
    assert snapshot["feature_count"] == len(snapshot["features"])
    if not all(snapshot["sources"].get(source, {}).get("last_ok") for source in ("metno", "sachet")):
        assert snapshot["stale"], "missing source provenance must never read as fresh"
    print("PASS snapshot; features:", snapshot["feature_count"], "stale:", snapshot["stale"])

    code, raw = request(args.url, "/v1/route", {
        "origin": {"lat": 12.9719, "lon": 77.6412},
        "destination": {"lat": 12.9172, "lon": 77.6228},
        "vclass": "car",
        "depart_at": datetime.now(timezone.utc).isoformat(),
        "lang": "en",
    })
    route = json.loads(raw)
    if code == 502 and not args.require_route:
        assert route["detail"] == "routing temporarily unavailable", route
        print("PASS unavailable router fails honestly with 502; route geometry NOT verified")
    else:
        assert code == 200, ("route", code, route)
        if args.require_route:
            assert route["routes"], ("no drivable route returned", route)
        for item in route["routes"]:
            assert len(item["geometry"]) > 10 and item["eta_min"] > 0, item
        assert route["routes"] or route["no_safe_route"], route
        print("PASS route; options:", len(route["routes"]), "no_safe_route:", route["no_safe_route"])

    if args.report:
        # Outside the seeded Bengaluru inventory: test submission cannot become road evidence.
        code, raw = request(args.url, "/v1/reports", {
            "lat": 8.1, "lon": 80.1, "depth_class": "wet", "reporter_id": "smoke_test_unmatched",
        })
        report = json.loads(raw)
        assert code == 201 and report["status"] == "received", ("report", code, report)
        assert report["segment_id"] is None, "synthetic smoke report unexpectedly matched a road"
        print("PASS synthetic unmatched report; id:", report["report_id"])


if __name__ == "__main__":
    main()
