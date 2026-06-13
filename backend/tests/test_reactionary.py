"""Unit tests for knock-on (reactionary) delay propagation.

These test the engine directly (no running server needed), unlike the
integration suites in this directory.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulation as sim  # noqa: E402


def _flight(callsign, reg, std, block_min, delay=0, status="scheduled", note=""):
    base = "2026-06-12T"
    std_iso = f"{base}{std}:00+00:00"
    sta = sim._add_minutes_to_clock(std_iso, block_min)
    return {
        "id": f"FLT-{callsign}",
        "callsign": callsign,
        "origin": "LHR",
        "destination": "CDG",
        "std": std_iso,
        "sta": sta,
        "block_min": block_min,
        "aircraft_reg": reg,
        "aircraft_type": "A320",
        "status": status,
        "delay_min": delay,
        "pax_count": 150,
        "assigned_crew_ids": [],
        "required_crew": {"CP": 1, "FO": 1, "SC": 1, "CC": 3, "type_qual": "A320"},
        "pairing_id": f"PAIR-{callsign}",
        "note": note,
    }


def _state(flights):
    return {"flights": flights, "crew": [], "kpis": {}}


def test_late_inbound_pushes_next_sector():
    # A departs 06:00+60 late, block 75 → arrives 08:15, ready 09:00 (45m turn).
    # B scheduled 08:30 on the same tail → must slip 30 min.
    a = _flight("EGW100", "G-EAGA", "06:00", 75, delay=60, status="delayed")
    b = _flight("EGW102", "G-EAGA", "08:30", 75)
    state = _state([a, b])
    affected = sim.propagate_reactionary_delays(state)
    assert b["delay_min"] == 30
    assert b["reactionary_min"] == 30
    assert b["status"] == "delayed"
    assert b["note"].startswith("REACTIONARY")
    assert "EGW100" in b["note"]
    assert affected and affected[0]["callsign"] == "EGW102"
    assert affected[0]["added_min"] == 30


def test_propagation_is_idempotent():
    a = _flight("EGW100", "G-EAGA", "06:00", 75, delay=60, status="delayed")
    b = _flight("EGW102", "G-EAGA", "08:30", 75)
    state = _state([a, b])
    sim.propagate_reactionary_delays(state)
    again = sim.propagate_reactionary_delays(state)
    assert again == []
    assert b["delay_min"] == 30
    assert b["reactionary_min"] == 30


def test_growing_inbound_delay_adds_only_the_difference():
    a = _flight("EGW100", "G-EAGA", "06:00", 75, delay=60, status="delayed")
    b = _flight("EGW102", "G-EAGA", "08:30", 75)
    state = _state([a, b])
    sim.propagate_reactionary_delays(state)
    a["delay_min"] += 30  # inbound slips further
    sim.propagate_reactionary_delays(state)
    assert b["delay_min"] == 60
    assert b["reactionary_min"] == 60


def test_cascade_rolls_through_the_whole_rotation():
    # Three back-to-back sectors, first one heavily delayed.
    a = _flight("EGW100", "G-EAGA", "06:00", 75, delay=120, status="delayed")
    b = _flight("EGW102", "G-EAGA", "08:30", 75)
    c = _flight("EGW104", "G-EAGA", "11:00", 75)
    state = _state([a, b, c])
    sim.propagate_reactionary_delays(state)
    # A: dep 08:00, arr 09:15, ready 10:00 → B slips 90 (08:30→10:00)
    assert b["reactionary_min"] == 90
    # B: dep 10:00, arr 11:15, ready 12:00 → C slips 60 (11:00→12:00)
    assert c["reactionary_min"] == 60
    assert "EGW102" in c["note"]


def test_cancelled_sector_does_not_propagate():
    a = _flight("EGW100", "G-EAGA", "06:00", 75, delay=240, status="cancelled")
    b = _flight("EGW102", "G-EAGA", "08:30", 75)
    state = _state([a, b])
    affected = sim.propagate_reactionary_delays(state)
    assert affected == []
    assert b["delay_min"] == 0
    assert b.get("reactionary_min", 0) == 0


def test_slack_in_schedule_absorbs_delay():
    # 06:00+15 late, block 75 → arr 07:30, ready 08:15; B at 09:00 is unaffected.
    a = _flight("EGW100", "G-EAGA", "06:00", 75, delay=15, status="delayed")
    b = _flight("EGW102", "G-EAGA", "09:00", 75)
    state = _state([a, b])
    assert sim.propagate_reactionary_delays(state) == []
    assert b["delay_min"] == 0


def test_other_tail_unaffected():
    a = _flight("EGW100", "G-EAGA", "06:00", 75, delay=120, status="delayed")
    b = _flight("EGW200", "G-EAGB", "08:30", 75)
    state = _state([a, b])
    sim.propagate_reactionary_delays(state)
    assert b["delay_min"] == 0


def test_departed_flights_are_not_touched():
    a = _flight("EGW100", "G-EAGA", "06:00", 75, delay=60, status="delayed")
    b = _flight("EGW102", "G-EAGA", "08:30", 75, status="airborne")
    state = _state([a, b])
    affected = sim.propagate_reactionary_delays(state)
    assert affected == []
    assert b["delay_min"] == 0


def test_night_stop_note_not_clobbered():
    a = _flight("EGW100", "G-EAGA", "06:00", 75, delay=60, status="delayed")
    b = _flight("EGW102", "G-EAGA", "08:30", 75, note="RETURN FROM NIGHT-STOP crew")
    state = _state([a, b])
    sim.propagate_reactionary_delays(state)
    assert b["reactionary_min"] == 30
    assert b["note"].startswith("RETURN FROM NIGHT-STOP")
