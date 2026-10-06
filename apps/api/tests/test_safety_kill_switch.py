"""Tests for Safety Case emergency kill switch and advisory freeze (TRD 16)."""

from __future__ import annotations

import pytest

from floodroute.safety.kill_switch import (
    disengage_kill_switch,
    engage_kill_switch,
    get_active_kill_switch,
    list_kill_switches,
)


def test_engage_and_get_active_kill_switch(app_db):
    # Initially inactive
    assert get_active_kill_switch(app_db) is None

    # Engage global kill switch
    rec = engage_kill_switch(
        conn=app_db,
        scope="global",
        reason="Sensor telemetry drift detected during storm",
        operator_id="op_commander",
        notes="Precautionary freeze",
    )
    assert rec.is_active is True
    assert rec.scope == "global"
    assert rec.operator_id == "op_commander"

    # Query active
    active = get_active_kill_switch(app_db)
    assert active is not None
    assert active.switch_id == rec.switch_id

    # Verify audit log entry
    audit = app_db.execute(
        "select actor, action, reason from audit_log where action = 'kill_switch_engaged'"
    ).fetchone()
    assert audit is not None
    assert audit[0] == "op_commander"
    assert "telemetry drift" in audit[2]


def test_engage_validation_rules(app_db):
    # Short reason rejected
    with pytest.raises(ValueError, match="at least 5 characters"):
        engage_kill_switch(
            conn=app_db,
            scope="global",
            reason="bad",
            operator_id="op1",
        )

    # Empty operator rejected
    with pytest.raises(ValueError, match="Operator ID is required"):
        engage_kill_switch(
            conn=app_db,
            scope="global",
            reason="Valid reason but missing op",
            operator_id="   ",
        )

    # Tenant scope without tenant_id rejected
    with pytest.raises(ValueError, match="Tenant ID is required"):
        engage_kill_switch(
            conn=app_db,
            scope="tenant",
            reason="Tenant specific failure",
            operator_id="op1",
        )


def test_disengage_enforces_two_operator_co_verification(app_db):
    rec = engage_kill_switch(
        conn=app_db,
        scope="global",
        reason="Temporary system test freeze",
        operator_id="operator_alpha",
    )

    # Single operator cannot release kill switch
    with pytest.raises(ValueError, match="Two distinct operators required"):
        disengage_kill_switch(
            conn=app_db,
            switch_id=rec.switch_id,
            reason="Sensor calibrated and verified",
            operator_id="operator_alpha",
            second_operator_id="operator_alpha",
        )

    # Two distinct operators succeed
    released = disengage_kill_switch(
        conn=app_db,
        switch_id=rec.switch_id,
        reason="Sensor telemetry verified against ground radar",
        operator_id="operator_alpha",
        second_operator_id="operator_beta",
        notes="Verified nominal",
    )
    assert released.is_active is False
    assert released.second_operator_id == "operator_beta"
    assert released.disengaged_at is not None

    # Query active returns None now
    assert get_active_kill_switch(app_db) is None

    # Audit log records co-verification
    audit = app_db.execute(
        "select actor, action from audit_log where action = 'kill_switch_disengaged'"
    ).fetchone()
    assert audit is not None
    assert audit[0] == "operator_alpha+operator_beta"


def test_list_kill_switches_history(app_db):
    r1 = engage_kill_switch(
        conn=app_db,
        scope="global",
        reason="First drill freeze test",
        operator_id="op1",
    )
    disengage_kill_switch(
        conn=app_db,
        switch_id=r1.switch_id,
        reason="Drill completed",
        operator_id="op1",
        second_operator_id="op2",
    )

    r2 = engage_kill_switch(
        conn=app_db,
        scope="global",
        reason="Second freeze test",
        operator_id="op3",
    )

    all_switches = list_kill_switches(app_db, active_only=False)
    assert len(all_switches) >= 2

    active_only = list_kill_switches(app_db, active_only=True)
    assert len(active_only) == 1
    assert active_only[0].switch_id == r2.switch_id
