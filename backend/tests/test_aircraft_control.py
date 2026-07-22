"""Unit tests for the Aircraft Control desk: the fleet view, tail-to-rotation
assignment, and its hard legality constraints (type, overlap, in-progress).

Pure engine tests (no server), following the test_curfew.py pattern.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulation as sim  # noqa: E402


@pytest.fixture(autouse=True)
def _no_random_spawns(monkeypatch):
    """Zero incident spawning so ticks used to depart flights don't add stray
    delay that could perturb the exact assertions."""
    monkeypatch.setattr(sim, "BASE_INCIDENT_RATE_PER_HOUR", 0)


def _flight(callsign, reg, ac_type, std, block_min, pairing_id, status="scheduled"):
    std_iso = f"2026-06-12T{std}:00+00:00"
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
        "aircraft_type": ac_type,
        "status": status,
        "delay_min": 0,
        "pax_count": 150,
        "assigned_crew_ids": [],
        "required_crew": {"CP": 1, "FO": 1, "SC": 1, "CC": 4, "type_qual": ac_type},
        "pairing_id": pairing_id,
        "note": "",
    }


def _state(flights, fleet=None, phase="ROSTER"):
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
        "kpis": {},
    }


# ---- Fleet spec / generation ----

def test_new_game_has_spare_tails_that_dont_fly():
    state = sim.new_game("free_play")
    spares = [a for a in state["fleet"] if a.get("spare")]
    assert len(spares) == 3
    flown_regs = {f["aircraft_reg"] for f in state["flights"]}
    for sp in spares:
        assert sp["reg"] not in flown_regs, "a spare tail must not be scheduled to fly"


# ---- aircraft_control view ----

def test_aircraft_control_view_shape():
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1"),
        _flight("EGW102", "G-EAGA", "A320", "08:30", 75, "P1"),  # same pairing (out+back)
        _flight("EGW200", "G-EAGB", "A320", "07:00", 90, "P2"),
    ]
    v = sim.aircraft_control(_state(flights))
    assert {t["reg"] for t in v["fleet"]} == {"G-EAGA", "G-EAGB", "G-EAGE", "G-EAGN"}
    spare = next(t for t in v["fleet"] if t["reg"] == "G-EAGE")
    assert spare["spare"] and spare["status"] == "spare" and spare["rotation_count"] == 0
    a = next(t for t in v["fleet"] if t["reg"] == "G-EAGA")
    assert a["rotation_count"] == 1 and a["sectors"] == 2  # one pairing, two sectors
    assert len(v["rotations"]) == 2  # P1 and P2
    p1 = next(r for r in v["rotations"] if r["pairing_id"] == "P1")
    assert p1["callsigns"] == ["EGW100", "EGW102"]
    assert p1["reassignable"] is True


# ---- Assignment happy path ----

def test_assign_spare_moves_whole_pairing():
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1"),
        _flight("EGW102", "G-EAGA", "A320", "08:30", 75, "P1"),
    ]
    state = _state(flights)
    res = sim.assign_aircraft(state, "P1", "G-EAGE")
    assert res["applied"] is True
    assert res["previous_reg"] == "G-EAGA"
    assert {f["aircraft_reg"] for f in flights} == {"G-EAGE"}


# ---- Hard constraints ----

def test_type_mismatch_blocked():
    flights = [_flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1")]
    state = _state(flights)
    w = sim.check_aircraft_assignment(state, "P1", "G-EAGN")  # B777 onto A320 rotation
    assert any(x["code"] == "AC_TYPE_MISMATCH" for x in w)
    res = sim.assign_aircraft(state, "P1", "G-EAGN")
    assert res["applied"] is False
    assert flights[0]["aircraft_reg"] == "G-EAGA"  # unchanged


def test_overlap_blocked():
    # G-EAGB already flies P2 (07:00-08:30). Putting P1 (06:00-07:15) on G-EAGB
    # overlaps once the 45-min turnaround is considered.
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1"),
        _flight("EGW200", "G-EAGB", "A320", "07:00", 90, "P2"),
    ]
    state = _state(flights)
    w = sim.check_aircraft_assignment(state, "P1", "G-EAGB")
    assert any(x["code"] == "AC_OVERLAP" for x in w)
    res = sim.assign_aircraft(state, "P1", "G-EAGB")
    assert res["applied"] is False


def test_non_overlapping_same_tail_allowed():
    # P1 finishes 07:15; P3 starts 09:00 — comfortably clear of the turnaround,
    # so both can sit on the same spare tail.
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1"),
        _flight("EGW300", "G-EAGE", "A320", "09:00", 75, "P3"),
    ]
    state = _state(flights)
    w = sim.check_aircraft_assignment(state, "P1", "G-EAGE")
    assert w == []
    assert sim.assign_aircraft(state, "P1", "G-EAGE")["applied"] is True


def test_in_progress_rotation_not_reassignable():
    flights = [_flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1", status="airborne")]
    state = _state(flights)
    w = sim.check_aircraft_assignment(state, "P1", "G-EAGE")
    assert any(x["code"] == "AC_DEPARTED" for x in w)
    v = sim.aircraft_control(state)
    assert next(r for r in v["rotations"] if r["pairing_id"] == "P1")["reassignable"] is False


def test_unknown_reference_returns_critical():
    state = _state([_flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1")])
    assert sim.check_aircraft_assignment(state, "NOPE", "G-EAGA")[0]["code"] == "REF_NOT_FOUND"
    assert sim.check_aircraft_assignment(state, "P1", "G-NONE")[0]["code"] == "REF_NOT_FOUND"


def test_reassign_to_same_reg_is_noop_success():
    flights = [_flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1")]
    state = _state(flights)
    res = sim.assign_aircraft(state, "P1", "G-EAGA")
    assert res["applied"] is True
    assert flights[0]["aircraft_reg"] == "G-EAGA"


def test_cancelled_pairing_does_not_block_overlap():
    # A cancelled rotation on a tail frees that tail for other flying.
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1"),
        _flight("EGW200", "G-EAGE", "A320", "06:30", 90, "P2", status="cancelled"),
    ]
    state = _state(flights)
    assert sim.check_aircraft_assignment(state, "P1", "G-EAGE") == []
