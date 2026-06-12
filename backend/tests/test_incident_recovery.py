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


def test_mel_defer_infeasible_on_major_tech():
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    opts = sim._recovery_options_for(state, flight, "TECH", "major")
    mel = next(o for o in opts if o["action"] == "mel_defer")
    assert mel["feasible"] is False
    inc = _make_incident(state, flight, "TECH", "major")
    res = sim.resolve_incident(state, inc["id"], "mel_defer")
    assert res["ok"] is False
    assert inc["status"] == "open"  # refused, still open


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


def test_aircraft_swap_requires_actually_spare_tail():
    state = _fresh_ops_state()
    flight = _staffed_flight(state)
    same_type = [a for a in state["fleet"] if a["type"] == flight["aircraft_type"]]
    spare = sim._find_spare_aircraft(state, flight)
    if spare is not None:
        # the returned tail must have no remaining active sector
        active = ("scheduled", "delayed", "boarding", "airborne")
        assert not any(
            f["aircraft_reg"] == spare["reg"] and f["status"] in active
            for f in state["flights"]
        )
    else:
        # every other same-type tail is busy — that's exactly why it's None
        for ac in same_type:
            if ac["reg"] == flight["aircraft_reg"]:
                continue
            assert any(
                f["aircraft_reg"] == ac["reg"]
                and f["status"] in ("scheduled", "delayed", "boarding", "airborne")
                for f in state["flights"]
            )
