"""Tests for state-aware incident recovery: options reflect the live operation
and resolutions genuinely mutate the roster (engine-level, no HTTP)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import simulation as sim


def _fresh_ops_state():
    state = sim.new_game("free_play")
    sim.auto_roster(state)
    sim.start_day(state)
    return state


def _staffed_flight(state):
    """A fully-staffed, not-departed flight."""
    for f in state["flights"]:
        if f["status"] == "scheduled" and f["assigned_crew_ids"]:
            req = f["required_crew"]
            if len(f["assigned_crew_ids"]) >= req["CP"] + req["FO"] + req["SC"] + req["CC"]:
                return f
    return next(f for f in state["flights"] if f["assigned_crew_ids"])


def _make_incident(state, flight, kind, sev="minor"):
    inc = {
        "id": "INC-TEST01",
        "type": kind,
        "severity": sev,
        "description": "test",
        "raised_at": state["clock"],
        "flight_id": flight["id"],
        "flight_callsign": flight["callsign"],
        "status": "open",
        "resolution": None,
        "options": sim._recovery_options_for(state, flight, kind, sev),
    }
    state["incidents"].append(inc)
    return inc


def test_options_carry_feasibility_and_dynamic_costs():
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    opts = sim._recovery_options_for(state, flight, "CREW_SICK", "minor")
    by_action = {o["action"]: o for o in opts}
    assert "feasible" in by_action["callout_standby"]
    # delay cost scales with pax — never the old flat 5000 for every flight
    assert by_action["delay"]["cost_usd"] == int(1500 + flight["pax_count"] * 12)
    # infeasible options must say why
    for o in opts:
        if o["feasible"] is False:
            assert o["reason"]


def test_major_tech_is_cancel_only_and_pauses_the_clock():
    # A grounded (major) tech defect isn't MEL-deferrable and can't just be
    # held for — the only queue-resolvable option is cancel; fixing it any
    # other way means going to Aircraft Control, and the whole clock is
    # frozen until the player does one or the other.
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    opts = sim._recovery_options_for(state, flight, "TECH", "major")
    assert {o["action"] for o in opts} == {"cancel"}

    inc = _make_incident(state, flight, "TECH", "major")
    inc["requires_aircraft_decision"] = True
    assert sim.is_clock_paused(state) is True
    res = sim.tick(state)
    assert res.get("paused") is True

    res = sim.resolve_incident(state, inc["id"], "mel_defer")
    assert res["ok"] is False
    assert inc["status"] == "open"  # invalid action for this incident, refused

    res = sim.resolve_incident(state, inc["id"], "cancel")
    assert res["ok"] is True
    assert inc["status"] == "resolved"
    assert inc["decision_grade"]["player_choice"] == "cancel"
    assert sim.is_clock_paused(state) is False


def test_mel_defer_opens_a_structured_deferral_on_the_tail():
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    ac = next(a for a in state["fleet"] if a["reg"] == flight["aircraft_reg"])
    assert ac.get("mel_items", []) == []

    inc = _make_incident(state, flight, "TECH", "minor")
    res = sim.resolve_incident(state, inc["id"], "mel_defer")
    assert res["ok"] is True

    items = ac["mel_items"]
    assert len(items) == 1
    item = items[0]
    assert item["category"] in ("B", "C")
    assert item["days_remaining"] == sim.MEL_CATEGORY_LIMITS_DAYS[item["category"]]
    assert item["expired"] is False
    assert str(item["days_remaining"]) in flight["note"]


def test_mel_deferral_grounds_the_tail_once_expired():
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    ac = next(a for a in state["fleet"] if a["reg"] == flight["aircraft_reg"])
    ac["mel_items"] = [{"id": "MEL-X", "category": "B", "note": "test", "days_remaining": 0, "expired": True}]

    pairing_id = flight["pairing_id"]
    other_reg = next(a["reg"] for a in state["fleet"] if a["reg"] != ac["reg"] and a["type"] == ac["type"])
    w = sim.check_aircraft_assignment(state, pairing_id, ac["reg"])
    assert any(x["code"] == "AC_MEL_EXPIRED" for x in w)
    # An unaffected tail of the same type is unaffected by another tail's MEL state.
    w_other = sim.check_aircraft_assignment(state, pairing_id, other_reg)
    assert not any(x["code"] == "AC_MEL_EXPIRED" for x in w_other)


def test_overnight_rectification_counts_down_and_can_expire(monkeypatch):
    state = _fresh_ops_state()
    ac = state["fleet"][0]
    ac["mel_items"] = [{"id": "MEL-X", "category": "B", "note": "test", "days_remaining": 1, "expired": False}]
    # Force this item to survive the overnight-clear roll so it counts down.
    monkeypatch.setattr(sim.random, "random", lambda: 1.0)
    sim.advance_to_next_day(state)
    item = ac["mel_items"][0]
    assert item["days_remaining"] == 0
    assert item["expired"] is True


def test_overnight_rectification_can_clear_the_item(monkeypatch):
    state = _fresh_ops_state()
    ac = state["fleet"][0]
    ac["mel_items"] = [{"id": "MEL-X", "category": "C", "note": "test", "days_remaining": 5, "expired": False}]
    # Force the overnight-clear roll to succeed.
    monkeypatch.setattr(sim.random, "random", lambda: 0.0)
    sim.advance_to_next_day(state)
    assert ac["mel_items"] == []


def test_callout_standby_consumes_real_standby():
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    # make a gap: pull one assigned crew off (simulate sickness)
    cid = flight["assigned_crew_ids"][0]
    crew = next(c for c in state["crew"] if c["id"] == cid)
    crew["status"] = "sick"
    crew["assigned_flight_id"] = None
    for pf in state["flights"]:
        if cid in pf["assigned_crew_ids"]:
            pf["assigned_crew_ids"].remove(cid)

    inc = _make_incident(state, flight, "CREW_SICK")
    opt = next(o for o in inc["options"] if o["action"] == "callout_standby")
    cost_before = state["kpis"]["cost_usd"]
    res = sim.resolve_incident(state, inc["id"], "callout_standby")
    if opt["feasible"]:
        assert res["ok"] is True
        rid = inc["replacement_crew_id"]
        replacement = next(c for c in state["crew"] if c["id"] == rid)
        assert replacement["status"] == "on_duty"          # actually consumed
        assert rid in flight["assigned_crew_ids"]          # actually on the flight
        assert state["kpis"]["cost_usd"] > cost_before     # charged
    else:
        assert res["ok"] is False
        assert state["kpis"]["cost_usd"] == cost_before    # NOT charged on refusal
        assert inc["status"] == "open"


def test_cancel_releases_crew_and_cascades_pairing():
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    crew_ids = list(flight["assigned_crew_ids"])
    assert crew_ids
    siblings = [
        f for f in state["flights"]
        if f.get("pairing_id") == flight.get("pairing_id") and f["status"] == "scheduled"
    ]
    inc = _make_incident(state, flight, "WEATHER")
    res = sim.resolve_incident(state, inc["id"], "cancel")
    assert res["ok"] is True
    for f in siblings:
        assert f["status"] == "cancelled"
    for cid in crew_ids:
        c = next(c for c in state["crew"] if c["id"] == cid)
        # crew no longer tied to a cancelled duty
        assert not any(
            cid in f["assigned_crew_ids"] for f in state["flights"] if f["status"] == "cancelled"
        )
        assert c["status"] != "on_duty"


def test_aircraft_control_reassignment_resolves_the_pending_incident_and_grades_it():
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    same_type_other = next(
        a for a in state["fleet"]
        if a["type"] == flight["aircraft_type"] and a["reg"] != flight["aircraft_reg"]
    )
    inc = _make_incident(state, flight, "TECH", "major")
    inc["requires_aircraft_decision"] = True
    assert sim.is_clock_paused(state) is True

    pairing_id = flight["pairing_id"]
    # Free up the candidate tail so the reassignment is actually legal.
    for f in state["flights"]:
        if f["aircraft_reg"] == same_type_other["reg"] and f.get("pairing_id") != pairing_id:
            f["status"] = "cancelled"

    res = sim.assign_aircraft(state, pairing_id, same_type_other["reg"])
    assert res["applied"] is True
    assert res["incident_resolved"] == inc["id"]
    assert res["decision_grade"]["player_choice"] == same_type_other["reg"]
    assert res["decision_grade"]["verdict"] in ("OPTIMAL", "GOOD", "SUBOPTIMAL")
    assert inc["status"] == "resolved"
    assert inc["decision_grade"] == res["decision_grade"]
    assert sim.is_clock_paused(state) is False


def test_best_aircraft_decision_never_recommends_the_grounded_tail_itself():
    # The tail already on the pairing is the one that's grounded — it must
    # never be offered back as its own "best available" replacement, even
    # though check_aircraft_assignment has no opinion on WHY a tail needs
    # swapping and would otherwise consider it a same-reg no-op success.
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    best = sim._best_aircraft_decision(state, flight["pairing_id"])
    assert best["choice"] != flight["aircraft_reg"]


def test_pending_aircraft_decision_lookup_only_matches_its_own_pairing():
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    other_pairing = next(
        f["pairing_id"] for f in state["flights"]
        if f["pairing_id"] != flight["pairing_id"]
    )
    inc = _make_incident(state, flight, "TECH", "major")
    inc["requires_aircraft_decision"] = True

    assert sim._pending_aircraft_decision_incident(state, flight["pairing_id"]) == inc
    assert sim._pending_aircraft_decision_incident(state, other_pairing) is None
