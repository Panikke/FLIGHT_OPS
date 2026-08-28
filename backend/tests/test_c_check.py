"""Unit tests for scheduled heavy maintenance (C-check): a KNOWN, multi-day
tail unavailability distinct from the reactive MEL/AOG grounding layer.

Every active (non-spare) tail is seeded with an upcoming C-check at game
start and always has its next date known in advance, mirroring how real
heavy-check slots are booked ~18 months ahead. While a tail is inside its
window it cannot be scheduled to fly, dispatched, or ferried — same
no-override hard-constraint pattern as every other aircraft-side check.

Pure engine tests (no server), following the test_aircraft_control.py /
test_ferry.py pattern.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulation as sim  # noqa: E402


@pytest.fixture(autouse=True)
def _no_random_spawns(monkeypatch):
    monkeypatch.setattr(sim, "BASE_INCIDENT_RATE_PER_HOUR", 0)


def _flight(callsign, reg, ac_type, std, block_min, pairing_id, status="scheduled",
            origin="LHR", destination="CDG"):
    std_iso = f"2026-06-12T{std}:00+00:00"
    sta = sim._add_minutes_to_clock(std_iso, block_min)
    return {
        "id": f"FLT-{callsign}",
        "callsign": callsign,
        "origin": origin,
        "destination": destination,
        "std": std_iso,
        "sta": sta,
        "block_min": block_min,
        "aircraft_reg": reg,
        "aircraft_type": ac_type,
        "status": status,
        "delay_min": 0,
        "reactionary_min": 0,
        "pax_count": 150,
        "assigned_crew_ids": [],
        "required_crew": {"CP": 1, "FO": 1, "SC": 1, "CC": 4, "type_qual": ac_type},
        "pairing_id": pairing_id,
        "note": "",
    }


def _state(flights, fleet=None, phase="ROSTER", day_number=1, clock="2026-06-12T04:00:00+00:00"):
    return {
        "flights": flights,
        "crew": [],
        "fleet": fleet or [
            {"reg": "G-EAGA", "type": "A320"},
            {"reg": "G-EAGB", "type": "A320"},
            {"reg": "G-EAGE", "type": "A320", "spare": True},
            {"reg": "G-EAGN", "type": "B777"},
        ],
        "phase": phase,
        "day_number": day_number,
        "clock": clock,
        "kpis": {},
    }


# ---- Seeding at new_game() ----

def test_new_game_seeds_a_future_c_check_for_every_active_tail():
    state = sim.new_game("free_play")
    for ac in state["fleet"]:
        if ac.get("spare"):
            assert "c_check" not in ac or ac["c_check"] is None
            continue
        cc = ac["c_check"]
        assert cc["start_day"] > 1, "day 1 must never open with a tail already down"
        assert cc["end_day"] >= cc["start_day"]

    flown_regs = {f["aircraft_reg"] for f in state["flights"]}
    for ac in state["fleet"]:
        cc = ac.get("c_check")
        if cc and cc["start_day"] <= 1 <= cc["end_day"]:
            assert ac["reg"] not in flown_regs


def test_c_check_windows_are_isolated_per_game():
    state_a = sim.new_game("free_play")
    state_b = sim.new_game("free_play")
    active_a = next(ac for ac in state_a["fleet"] if not ac.get("spare"))
    active_a["c_check"] = {"start_day": 1, "end_day": 1}
    active_b = next(ac for ac in state_b["fleet"] if ac["reg"] == active_a["reg"])
    assert active_b.get("c_check") != {"start_day": 1, "end_day": 1}


# ---- Day generation must respect a live C-check window ----

def test_generate_day_flights_skips_a_tail_mid_c_check():
    fleet = [
        {"reg": "G-EAGA", "type": "A320", "c_check": {"start_day": 1, "end_day": 5}},
        {"reg": "G-EAGB", "type": "A320"},
    ]
    flights = sim._generate_day_flights("2026-06-12T04:00:00+00:00", fleet, day_number=1)
    regs = {f["aircraft_reg"] for f in flights}
    assert "G-EAGA" not in regs
    assert "G-EAGB" in regs


def test_generate_day_flights_uses_tail_once_its_window_has_passed():
    fleet = [{"reg": "G-EAGA", "type": "A320", "c_check": {"start_day": 1, "end_day": 5}}]
    flights = sim._generate_day_flights("2026-06-12T04:00:00+00:00", fleet, day_number=6)
    assert any(f["aircraft_reg"] == "G-EAGA" for f in flights)


def test_generate_next_day_flights_skips_a_tail_mid_c_check():
    fleet = [
        {"reg": "G-EAGA", "type": "A320", "c_check": {"start_day": 3, "end_day": 8}},
        {"reg": "G-EAGB", "type": "A320"},
    ]
    flights = sim._generate_next_day_flights(
        "2026-06-13T04:00:00+00:00", {}, [], fleet=fleet, day_number=5)
    regs = {f["aircraft_reg"] for f in flights}
    assert "G-EAGA" not in regs
    assert "G-EAGB" in regs


# ---- Hard block on dispatch/reassignment/ferry ----

def test_check_aircraft_assignment_blocks_during_c_check():
    flights = [_flight("EGW100", "G-EAGB", "A320", "06:00", 75, "P1")]
    fleet = [
        {"reg": "G-EAGA", "type": "A320", "c_check": {"start_day": 1, "end_day": 5}},
        {"reg": "G-EAGB", "type": "A320"},
    ]
    state = _state(flights, fleet=fleet, day_number=1)
    w = sim.check_aircraft_assignment(state, "P1", "G-EAGA")
    assert any(x["code"] == "AC_IN_MAINTENANCE" for x in w)
    res = sim.assign_aircraft(state, "P1", "G-EAGA")
    assert res["applied"] is False
    assert flights[0]["aircraft_reg"] == "G-EAGB"


def test_check_aircraft_assignment_allows_once_c_check_window_passes():
    flights = [_flight("EGW100", "G-EAGB", "A320", "06:00", 75, "P1")]
    fleet = [
        {"reg": "G-EAGA", "type": "A320", "c_check": {"start_day": 1, "end_day": 5}},
        {"reg": "G-EAGB", "type": "A320"},
    ]
    state = _state(flights, fleet=fleet, day_number=6)
    w = sim.check_aircraft_assignment(state, "P1", "G-EAGA")
    assert not any(x["code"] == "AC_IN_MAINTENANCE" for x in w)


def test_check_ferry_blocks_during_c_check():
    flights = [_flight("EGW100", "G-EAGB", "A320", "06:00", 75, "P1")]
    fleet = [
        {"reg": "G-EAGA", "type": "A320", "c_check": {"start_day": 1, "end_day": 5}},
        {"reg": "G-EAGB", "type": "A320"},
    ]
    state = _state(flights, fleet=fleet, day_number=1)
    w = sim.check_ferry(state, "P1", "G-EAGA")
    assert any(x["code"] == "AC_IN_MAINTENANCE" for x in w)


def test_no_override_for_c_check_via_substitution():
    # An off-type substitution still routes through check_aircraft_assignment
    # for anything that isn't the type gate — C-check must survive that.
    flights = [_flight("EGW100", "G-EAGN", "B777", "06:00", 300, "P1", origin="LHR", destination="JFK")]
    fleet = [
        {"reg": "G-EAGN", "type": "B777"},
        {"reg": "G-EAGL", "type": "A350", "c_check": {"start_day": 1, "end_day": 5}},
    ]
    state = _state(flights, fleet=fleet, day_number=1)
    w = sim.check_substitution(state, "P1", "G-EAGL")
    assert any(x["code"] == "AC_IN_MAINTENANCE" for x in w)


# ---- aircraft_control() view ----

def test_aircraft_control_reports_c_check_status():
    fleet = [
        {"reg": "G-EAGA", "type": "A320", "c_check": {"start_day": 1, "end_day": 5}},
        {"reg": "G-EAGB", "type": "A320", "c_check": {"start_day": 20, "end_day": 25}},
    ]
    state = _state([], fleet=fleet, day_number=1)
    v = sim.aircraft_control(state)
    a = next(t for t in v["fleet"] if t["reg"] == "G-EAGA")
    b = next(t for t in v["fleet"] if t["reg"] == "G-EAGB")
    assert a["status"] == "c-check" and a["in_c_check"] is True
    assert a["c_check"] == {"start_day": 1, "end_day": 5}
    # Upcoming (not yet started) still surfaces the date, just not as the
    # active status — this is the forward-planning visibility the mechanic
    # exists for.
    assert b["in_c_check"] is False
    assert b["c_check"] == {"start_day": 20, "end_day": 25}
    assert v["day_number"] == 1


# ---- Rescheduling across a day boundary ----

def test_advance_to_next_day_reschedules_c_check_once_window_passes():
    state = sim.new_game("free_play")
    active = next(ac for ac in state["fleet"] if not ac.get("spare"))
    day = state["day_number"]
    active["c_check"] = {"start_day": day, "end_day": day}  # ends today
    sim.advance_to_next_day(state)
    rolled = next(ac for ac in state["fleet"] if ac["reg"] == active["reg"])
    assert rolled["c_check"]["start_day"] > state["day_number"]


def test_advance_to_next_day_leaves_a_still_open_c_check_untouched():
    state = sim.new_game("free_play")
    active = next(ac for ac in state["fleet"] if not ac.get("spare"))
    day = state["day_number"]
    window = {"start_day": day, "end_day": day + 10}  # spans the rollover
    active["c_check"] = dict(window)
    sim.advance_to_next_day(state)
    rolled = next(ac for ac in state["fleet"] if ac["reg"] == active["reg"])
    assert rolled["c_check"] == window
    # And the tail must not have been scheduled to fly the new day either.
    assert not any(f["aircraft_reg"] == active["reg"] for f in state["flights"])


def test_advance_to_next_day_does_not_schedule_c_check_for_spares():
    state = sim.new_game("free_play")
    spare = next(ac for ac in state["fleet"] if ac.get("spare"))
    sim.advance_to_next_day(state)
    rolled = next(ac for ac in state["fleet"] if ac["reg"] == spare["reg"])
    assert "c_check" not in rolled or rolled["c_check"] is None
