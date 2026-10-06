"""Safety case controls, emergency kill switches, and advisory freeze subsystem (TRD 16)."""

from floodroute.safety.kill_switch import (
    KillSwitchRecord,
    disengage_kill_switch,
    engage_kill_switch,
    get_active_kill_switch,
    list_kill_switches,
)

__all__ = [
    "KillSwitchRecord",
    "disengage_kill_switch",
    "engage_kill_switch",
    "get_active_kill_switch",
    "list_kill_switches",
]
