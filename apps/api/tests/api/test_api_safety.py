"""Tests for Safety Case emergency kill switch API routes (TRD 16)."""

from __future__ import annotations


def test_api_kill_switch_lifecycle_and_advisory_freeze(client, app_db):
    # 1. Initially active is false
    r_status = client.get("/v1/safety/kill-switch")
    assert r_status.status_code == 200
    assert r_status.json()["is_active"] is False
    assert r_status.json()["advisory_status"] == "active"

    # 2. Engage emergency kill switch
    engage_payload = {
        "scope": "global",
        "reason": "Suspected telemetry spoofing during flash flood",
        "operator_id": "op_chief",
        "notes": "Emergency freeze activated",
    }
    r_engage = client.post("/v1/safety/kill-switch", json=engage_payload)
    assert r_engage.status_code == 200
    data_engage = r_engage.json()
    assert data_engage["status"] == "engaged"
    switch_id = data_engage["record"]["switch_id"]

    # 3. Status confirms suspended
    r_status_after = client.get("/v1/safety/kill-switch")
    assert r_status_after.status_code == 200
    assert r_status_after.json()["is_active"] is True
    assert r_status_after.json()["advisory_status"] == "suspended"

    # 4. Calling reroute endpoint returns advisory_off
    reroute_payload = {
        "origin": {"lat": 12.97, "lon": 77.59},
        "destination": {"lat": 12.92, "lon": 77.62},
        "vclass": "car",
        "current_edges": [
            {
                "segment_id": 901,
                "travel_time_s": 120,
                "length_m": 500,
                "turn_off_after": True,
                "geometry": [{"lat": 12.97, "lon": 77.59}, {"lat": 12.95, "lon": 77.60}],
            }
        ],
        "profile": "citizen",
        "lang": "en",
    }
    r_reroute = client.post("/v1/route/reroute", json=reroute_payload)
    assert r_reroute.status_code == 200
    reroute_data = r_reroute.json()
    assert reroute_data["action"] == "keep"
    assert reroute_data["code"] == "advisory_off"
    assert "Emergency advisory freeze active" in reroute_data["reasons"][0]

    # 5. Disengage requires distinct operators
    fail_disengage = {
        "reason": "Telemetry verified against ground truth",
        "operator_id": "op_chief",
        "second_operator_id": "op_chief",
    }
    r_fail = client.post(f"/v1/safety/kill-switch/{switch_id}/disengage", json=fail_disengage)
    assert r_fail.status_code == 400
    assert "Two distinct operators required" in r_fail.json()["detail"]

    # 6. Disengage with two operators succeeds
    succ_disengage = {
        "reason": "Telemetry verified against ground truth and radar",
        "operator_id": "op_chief",
        "second_operator_id": "op_safety_officer",
        "notes": "Clear to resume advisories",
    }
    r_succ = client.post(f"/v1/safety/kill-switch/{switch_id}/disengage", json=succ_disengage)
    assert r_succ.status_code == 200
    assert r_succ.json()["status"] == "disengaged"

    # 7. Check history endpoint
    r_hist = client.get("/v1/safety/kill-switch/history")
    assert r_hist.status_code == 200
    hist_data = r_hist.json()
    assert hist_data["count"] >= 1
    assert hist_data["records"][0]["switch_id"] == switch_id
