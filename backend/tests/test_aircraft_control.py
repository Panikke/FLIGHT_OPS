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


# ---- Position / station check ----

def test_wrong_station_blocked():
    # P1 is a night-stop return departing JFK (the original outbound aircraft
    # is there, not at the hub). An idle hub-based spare can't operate it.
    flights = [_flight("EGW900", "G-EAGN", "B777", "05:00", 460, "P1", origin="JFK", destination="LHR")]
    fleet = [
        {"reg": "G-EAGN", "type": "B777"},
        {"reg": "G-EAGQ", "type": "B777", "spare": True},
    ]
    state = _state(flights, fleet=fleet)
    w = sim.check_aircraft_assignment(state, "P1", "G-EAGQ")
    assert any(x["code"] == "AC_WRONG_STATION" for x in w)
    res = sim.assign_aircraft(state, "P1", "G-EAGQ")
    assert res["applied"] is False
    assert flights[0]["aircraft_reg"] == "G-EAGN"  # unchanged


def test_correct_station_allowed_via_earlier_arrival():
    # G-EAGE flies P1 into JFK, landing well before P2's departure — it's
    # legitimately at JFK by then, so it can operate the JFK-origin P2.
    flights = [
        _flight("EGW100", "G-EAGE", "B777", "04:00", 100, "P1", origin="LHR", destination="JFK"),
        _flight("EGW900", "G-EAGN", "B777", "08:00", 300, "P2", origin="JFK", destination="LHR"),
    ]
    fleet = [
        {"reg": "G-EAGE", "type": "B777"},
        {"reg": "G-EAGN", "type": "B777"},
    ]
    state = _state(flights, fleet=fleet)
    w = sim.check_aircraft_assignment(state, "P2", "G-EAGE")
    assert not any(x["code"] == "AC_WRONG_STATION" for x in w)


# ---- Reactionary delay reset (tail-swap rebuild) ----

def test_reset_reactionary_delays_strips_stale_knock_on():
    f = _flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1")
    f["delay_min"] = 45
    f["reactionary_min"] = 30  # 15min direct (e.g. incident) + 30min reactionary
    f["status"] = "delayed"
    f["note"] = "REACTIONARY (IATA 93) · aircraft late"
    state = _state([f])
    sim.reset_reactionary_delays(state)
    assert f["delay_min"] == 15  # non-reactionary baseline preserved
    assert f["reactionary_min"] == 0
    assert f["note"] == ""
    assert f["status"] == "delayed"  # still delayed on its own merits


def test_reset_reactionary_delays_reverts_status_when_delay_was_purely_reactionary():
    f = _flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1")
    f["delay_min"] = 30
    f["reactionary_min"] = 30  # entirely reactionary
    f["status"] = "delayed"
    state = _state([f])
    sim.reset_reactionary_delays(state)
    assert f["delay_min"] == 0
    assert f["status"] == "scheduled"


def test_tail_swap_clears_stale_reactionary_delay():
    # G-EAGA flies P1 then P2 back-to-back; P1 picks up a direct 60min delay
    # (simulating an incident), which knocks P2's departure late too.
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1"),
        _flight("EGW200", "G-EAGA", "A320", "07:30", 75, "P2"),
    ]
    flights[0]["delay_min"] = 60
    flights[0]["status"] = "delayed"
    state = _state(flights, phase="OPS")
    sim.propagate_reactionary_delays(state)
    assert flights[1]["reactionary_min"] > 0
    assert flights[1]["delay_min"] == flights[1]["reactionary_min"]

    # Reassign P2 onto an idle hub spare — no more knock-on relationship to P1.
    res = sim.assign_aircraft(state, "P2", "G-EAGE")
    assert res["applied"] is True

    # Mirrors the server route: rebuild from baseline before re-propagating.
    sim.reset_reactionary_delays(state)
    sim.propagate_reactionary_delays(state)
    assert flights[1]["reactionary_min"] == 0
    assert flights[1]["delay_min"] == 0
    assert flights[1]["status"] == "scheduled"


# ---- Next-day generation must also skip spares ----

def test_next_day_generation_skips_spares():
    flights = sim._generate_next_day_flights("2026-06-13T04:00:00+00:00", {}, [])
    spare_regs = {ac["reg"] for ac in sim.FLEET if ac.get("spare")}
    used_regs = {f["aircraft_reg"] for f in flights}
    assert not (spare_regs & used_regs), "spare tails must stay idle on subsequent days too"
