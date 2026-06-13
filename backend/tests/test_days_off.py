"""Unit tests for the crew days-off model and statutory days-off rule.

These exercise the engine directly (no running server needed), like
test_reactionary.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulation as sim  # noqa: E402


def _flight(callsign="EGW100", reg="G-EAGA", std="06:00", block_min=90):
    std_iso = f"2026-06-13T{std}:00+00:00"
    return {
        "id": f"FLT-{callsign}",
        "callsign": callsign,
        "origin": "LHR",
        "destination": "CDG",
        "std": std_iso,
        "sta": sim._add_minutes_to_clock(std_iso, block_min),
        "block_min": block_min,
        "aircraft_reg": reg,
        "aircraft_type": "A320",
        "status": "scheduled",
        "delay_min": 0,
        "pax_count": 150,
        "assigned_crew_ids": [],
        "required_crew": {"CP": 1, "FO": 1, "SC": 1, "CC": 3, "type_qual": "A320"},
        "pairing_id": f"PAIR-{callsign}",
        "note": "",
    }


def _crew(cid="EGW1000", rank="CP", quals=("A320",), dso=0, status="available"):
    """A clean, fully-legal crew member except for whatever we set on dso."""
    return {
        "id": cid,
        "name": f"T. {cid}",
        "rank": rank,
        "rank_title": rank,
        "base": "LHR",
        "qualifications": list(quals),
        "fdp_used_min": 0,
        "block_28d_hr": 10.0,
        "duty_7d_hr": 5.0,
        "rest_hr_since_duty": 24.0,
        "status": status,
        "assigned_flight_id": None,
        "fatigue_score": 20,
        "sickness_risk": 0.02,
        "days_since_off": dso,
        "duty_history": [],
        "days_off_planned": [],
    }


def _state(flights, crew, day_number=1, phase="ROSTER"):
    return {
        "flights": flights,
        "crew": crew,
        "kpis": {"legality_breaches": 0, "score": 1000},
        "day_number": day_number,
        "day_start": "2026-06-13T04:00:00+00:00",
        "phase": phase,
    }


# ---------------- seeding ---------------- #

def test_new_game_seeds_days_off_fields():
    state = sim.new_game("free_play")
    for c in state["crew"]:
        assert 0 <= c["days_since_off"] <= 5
        assert isinstance(c["duty_history"], list) and len(c["duty_history"]) > 0
        assert c["days_off_planned"] == []


# ---------------- the statutory rule ---------------- #

def test_below_threshold_is_clean():
    f, c = _flight(), _crew(dso=2)
    warnings = sim.check_assignment(_state([f], [c]), f["id"], c["id"])
    codes = {w["code"] for w in warnings}
    assert "DAYS_OFF_DUE" not in codes and "DAYS_OFF_REQUIRED" not in codes


def test_warns_one_day_before_limit():
    f, c = _flight(), _crew(dso=sim.DAYS_OFF_WARN_AT)  # 5
    warnings = sim.check_assignment(_state([f], [c]), f["id"], c["id"])
    due = [w for w in warnings if w["code"] == "DAYS_OFF_DUE"]
    assert due and due[0]["severity"] == "warning"
    # still legal to assign — no critical from the days-off rule
    assert not any(w["code"] == "DAYS_OFF_REQUIRED" for w in warnings)


def test_blocks_at_limit():
    f, c = _flight(), _crew(dso=sim.MAX_CONSECUTIVE_DUTY_DAYS)  # 6
    warnings = sim.check_assignment(_state([f], [c]), f["id"], c["id"])
    req = [w for w in warnings if w["code"] == "DAYS_OFF_REQUIRED"]
    assert req and req[0]["severity"] == "critical"


def test_auto_roster_skips_crew_owed_a_day_off():
    # Only CP available is over the limit -> the CP slot must stay unfilled.
    f = _flight()
    over = _crew(cid="EGW1000", rank="CP", dso=sim.MAX_CONSECUTIVE_DUTY_DAYS)
    fo = _crew(cid="EGW1001", rank="FO", dso=0)
    sc = _crew(cid="EGW1002", rank="SC", dso=0)
    cc = [_crew(cid=f"EGW20{i}", rank="CC", dso=0) for i in range(3)]
    state = _state([f], [over, fo, sc, *cc])
    sim.auto_roster(state)
    assert over["id"] not in f["assigned_crew_ids"]      # blocked
    assert fo["id"] in f["assigned_crew_ids"]            # others filled


# ---------------- planning + advance ---------------- #

def test_set_day_off_rejects_past_day():
    c = _crew()
    state = _state([], [c], day_number=5)
    res = sim.set_day_off(state, c["id"], 4, True)
    assert res["ok"] is False and res["error"] == "cannot_change_past"


def test_planned_future_day_off_is_queued_then_honoured():
    state = sim.new_game("free_play")
    c = state["crew"][0]
    c["days_since_off"] = 3
    target = state["day_number"] + 1
    res = sim.set_day_off(state, c["id"], target, True)
    assert res["ok"] and target in c["days_off_planned"]

    sim.advance_to_next_day(state)
    rolled = next(x for x in state["crew"] if x["id"] == c["id"])
    assert state["day_number"] == target
    assert rolled["status"] == "off"           # plan honoured
    assert target not in rolled["days_off_planned"]  # plan consumed


def test_days_since_off_increments_on_duty_resets_on_off():
    state = sim.new_game("free_play")
    a, b = state["crew"][0], state["crew"][1]
    a["status"], a["days_since_off"] = "available", 3   # reserve day -> AVL
    b["status"], b["days_since_off"] = "off", 4         # day off -> OFF
    sim.advance_to_next_day(state)
    a2 = next(x for x in state["crew"] if x["id"] == a["id"])
    b2 = next(x for x in state["crew"] if x["id"] == b["id"])
    assert a2["duty_history"][-1] == "AVL" and a2["days_since_off"] == 4
    assert b2["duty_history"][-1] == "OFF" and b2["days_since_off"] == 0


# ---------------- calendar shape ---------------- #

def test_crew_roster_shape_and_today_cell():
    state = sim.new_game("free_play")
    r = sim.crew_roster(state, past_days=5, future_days=4)
    assert r["day_number"] == 1
    assert len(r["days"]) == 10 and len(r["columns"]) == 10
    assert len(r["crew"]) == len(state["crew"])
    row = r["crew"][0]
    assert len(row["cells"]) == 10
    today = next(c for c in row["cells"] if c["rel"] == "today")
    assert today["day"] == 1 and today["code"] in ("FLT", "SBY", "AVL", "OFF", "SICK")


def test_crew_roster_reflects_planned_off_in_future_cell():
    state = sim.new_game("free_play")
    c = state["crew"][0]
    target = state["day_number"] + 2
    sim.set_day_off(state, c["id"], target, True)
    r = sim.crew_roster(state)
    row = next(x for x in r["crew"] if x["crew_id"] == c["id"])
    cell = next(cl for cl in row["cells"] if cl["day"] == target)
    assert cell["planned_off"] is True and cell["code"] == "OFF"
