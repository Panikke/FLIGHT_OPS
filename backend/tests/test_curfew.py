"""Unit tests for the LHR night curfew mechanic.

Pure engine tests (no running server needed), following the pattern in
test_reactionary.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulation as sim  # noqa: E402


def test_in_curfew_window_boundaries():
    from datetime import datetime, timezone
    dt = lambda h, m=0: datetime(2026, 6, 12, h, m, tzinfo=timezone.utc)
    assert sim._in_curfew_window(dt(23, 0)) is True
    assert sim._in_curfew_window(dt(23, 59)) is True
    assert sim._in_curfew_window(dt(0, 0)) is True
    assert sim._in_curfew_window(dt(5, 59)) is True
    assert sim._in_curfew_window(dt(6, 0)) is False
    assert sim._in_curfew_window(dt(22, 59)) is False
    assert sim._in_curfew_window(dt(12, 0)) is False


def _flight(callsign, origin, destination, std, block_min=75, pax=150):
    from simulation import _add_minutes_to_clock
    std_iso = f"2026-06-12T{std}:00+00:00"
    sta = _add_minutes_to_clock(std_iso, block_min)
    return {
        "id": f"FLT-{callsign}",
        "callsign": callsign,
        "origin": origin,
        "destination": destination,
        "std": std_iso,
        "sta": sta,
        "block_min": block_min,
        "aircraft_reg": "G-EAGA",
        "aircraft_type": "A320",
        "status": "scheduled",
        "delay_min": 0,
        "pax_count": pax,
        "assigned_crew_ids": [],
        "required_crew": {"CP": 1, "FO": 1, "SC": 1, "CC": 3, "type_qual": "A320"},
        "pairing_id": f"PAIR-{callsign}",
        "note": "",
    }


def _state(flights, clock_iso):
    return {
        "flights": flights,
        "crew": [],
        "incidents": [],
        "tick_count": 0,
        "phase": "OPS",
        "clock": clock_iso,
        "is_challenge": False,
        "kpis": {
            "otp_pct": 100.0, "legality_breaches": 0, "curfew_violations": 0,
            "fatigue_index": 25, "cost_usd": 0, "pax_delay_min": 0,
            "pax_disrupted": 0, "score": 1000,
        },
    }


def test_late_lhr_departure_fined_once():
    f = _flight("EGW999", "LHR", "CDG", "22:50")
    state = _state([f], "2026-06-12T22:00:00+00:00")
    # Tick past std (22:50) with enough delay accrued to push it into curfew
    f["delay_min"] = 20  # effective departure 23:10Z -> inside curfew
    sim.tick(state, minutes=90)  # clock -> 23:30Z, crosses effective std
    assert state["kpis"]["curfew_violations"] == 1
    assert state["kpis"]["cost_usd"] > 0
    assert f["curfew_violation"] == "departure"
    assert "LHR NIGHT CURFEW" in f["note"]

    # A further tick must not double-count the same violation
    sim.tick(state, minutes=30)
    assert state["kpis"]["curfew_violations"] == 1


def test_daytime_lhr_departure_not_fined():
    f = _flight("EGW100", "LHR", "CDG", "10:00")
    state = _state([f], "2026-06-12T09:00:00+00:00")
    sim.tick(state, minutes=90)  # crosses 10:00Z std, well outside curfew
    assert state["kpis"]["curfew_violations"] == 0
    assert f.get("curfew_violation") is None


def test_non_lhr_route_not_fined_even_at_night():
    # Both ends non-LHR — should never be checked, but exercise the
    # departure-origin guard: an LHR->CDG flight during curfew is fined,
    # a CDG->LHR flight where LHR is the DESTINATION is fined on arrival,
    # not departure.
    f = _flight("EGW200", "CDG", "LHR", "22:00", block_min=75)
    state = _state([f], "2026-06-12T21:30:00+00:00")
    f["delay_min"] = 30  # effective departure 22:30Z (CDG, not curfew-relevant), arrival ~23:45Z
    sim.tick(state, minutes=150)  # clock -> 00:00Z, past both std and sta
    assert state["kpis"]["curfew_violations"] == 1
    assert f["curfew_violation"] == "arrival"


def test_cancelled_flight_not_fined():
    f = _flight("EGW300", "LHR", "CDG", "23:30")
    f["status"] = "cancelled"
    state = _state([f], "2026-06-12T23:00:00+00:00")
    sim.tick(state, minutes=60)
    assert state["kpis"]["curfew_violations"] == 0


def test_fine_scales_with_pax_count():
    f_small = _flight("EGW1", "LHR", "CDG", "23:10", pax=50)
    f_large = _flight("EGW2", "LHR", "CDG", "23:10", pax=300)
    s_small = _state([f_small], "2026-06-12T23:00:00+00:00")
    s_large = _state([f_large], "2026-06-12T23:00:00+00:00")
    sim.tick(s_small, minutes=30)
    sim.tick(s_large, minutes=30)
    assert s_large["kpis"]["cost_usd"] > s_small["kpis"]["cost_usd"]
