"""Unit tests for the ferry (positioning-flight) recovery lever: dispatching
an empty, correctly-typed but wrongly-positioned tail to rescue a stranded
rotation, as distinct from a plain same-station reassignment.

A ferry needs a real minimum flight-deck crew (1 Captain + 1 First Officer),
that crew must be legal under the same EASA-FTL-inspired rest/duty checks as
any other duty, and the LHR night curfew can push its departure later —
these are exercised alongside the aircraft-side mechanics.

Pure engine tests (no server), following the test_aircraft_control.py pattern.
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


def _pilot(cid, rank, ac_type, status="available", rest_hr=24, fdp_used_min=0,
           duty_7d_hr=10, block_28d_hr=20, days_since_off=0, fatigue=20):
    return {
        "id": cid, "name": f"Test {rank} {cid}", "rank": rank, "rank_title": rank,
        "base": "LHR", "qualifications": [ac_type],
        "fdp_used_min": fdp_used_min, "block_28d_hr": block_28d_hr,
        "duty_7d_hr": duty_7d_hr, "rest_hr_since_duty": rest_hr,
        "status": status, "assigned_flight_id": None, "fatigue_score": fatigue,
        "sickness_risk": 0.02, "days_since_off": days_since_off,
        "duty_history": [], "days_off_planned": [],
    }


def _ferry_crew(ac_type="A320"):
    """One legal Captain + First Officer — the minimum a ferry needs."""
    return [_pilot("CP1", "CP", ac_type), _pilot("FO1", "FO", ac_type)]


def _state(flights, fleet=None, crew=None, clock="2026-06-12T09:00:00+00:00"):
    return {
        "flights": flights,
        "crew": crew if crew is not None else [],
        "fleet": fleet or [
            {"reg": "G-EAGA", "type": "A320"},
            {"reg": "G-EAGE", "type": "A320", "spare": True},
        ],
        "phase": "OPS",
        "clock": clock,
        "incidents": [],
        "decisions_log": [],
        "kpis": {
            "otp_pct": 100.0, "legality_breaches": 0, "cost_usd": 0,
            "pax_disrupted": 0, "fatigue_index": 0, "score": 1000,
        },
    }


# ---- check_ferry: what it deliberately does and doesn't block ----

def test_ferry_does_not_block_on_wrong_station():
    # G-EAGE is idle at the hub (LHR); the pairing needs a tail at MXP. A
    # plain reassignment would fail on AC_WRONG_STATION — ferry exists
    # precisely to solve that, so it must not block on it (given legal crew).
    flights = [_flight("EGW250", "G-EAGD", "A320", "07:00", 75, "P1", origin="MXP", destination="LHR")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=_ferry_crew())
    assert sim.check_aircraft_assignment(state, "P1", "G-EAGE") != []  # confirms the plain path IS blocked
    assert sim.check_ferry(state, "P1", "G-EAGE") == []


def test_ferry_blocks_on_type_mismatch():
    flights = [_flight("EGW900", "G-EAGN", "B777", "07:00", 75, "P1", origin="MXP", destination="LHR")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGN", "type": "B777"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ])
    w = sim.check_ferry(state, "P1", "G-EAGE")
    assert any(x["code"] == "AC_TYPE_MISMATCH" for x in w)


def test_ferry_blocks_when_candidate_tail_is_busy_elsewhere():
    flights = [
        _flight("EGW250", "G-EAGD", "A320", "07:00", 75, "P1", origin="MXP", destination="LHR"),
        _flight("EGW300", "G-EAGE", "A320", "07:30", 75, "P2", origin="LHR", destination="CDG"),
    ]
    state = _state(flights)
    w = sim.check_ferry(state, "P1", "G-EAGE")
    assert any(x["code"] == "AC_FERRY_BUSY" for x in w)


def test_ferry_blocks_on_fully_departed_pairing():
    flights = [_flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1", status="airborne")]
    state = _state(flights)
    w = sim.check_ferry(state, "P1", "G-EAGE")
    assert any(x["code"] == "AC_DEPARTED" for x in w)


def test_ferry_blocks_on_expired_mel():
    flights = [_flight("EGW250", "G-EAGD", "A320", "07:00", 75, "P1", origin="MXP", destination="LHR")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True,
         "mel_items": [{"id": "MEL-X", "category": "B", "note": "t", "days_remaining": 0, "expired": True}]},
    ])
    w = sim.check_ferry(state, "P1", "G-EAGE")
    assert any(x["code"] == "AC_MEL_EXPIRED" for x in w)


# ---- Minimum flight-deck crew (1) ----

def test_ferry_blocks_when_no_captain_available():
    flights = [_flight("EGW250", "G-EAGD", "A320", "07:00", 75, "P1", origin="MXP", destination="LHR")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=[_pilot("FO1", "FO", "A320")])  # FO only, no Captain at all
    w = sim.check_ferry(state, "P1", "G-EAGE")
    assert any(x["code"] == "FERRY_NO_CAPTAIN" for x in w)
    assert not any(x["code"] == "FERRY_NO_FO" for x in w)


def test_ferry_blocks_when_no_first_officer_available():
    flights = [_flight("EGW250", "G-EAGD", "A320", "07:00", 75, "P1", origin="MXP", destination="LHR")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=[_pilot("CP1", "CP", "A320")])  # Captain only, no FO at all
    w = sim.check_ferry(state, "P1", "G-EAGE")
    assert any(x["code"] == "FERRY_NO_FO" for x in w)


def test_ferry_blocks_when_pilots_are_not_type_rated():
    flights = [_flight("EGW250", "G-EAGD", "A320", "07:00", 75, "P1", origin="MXP", destination="LHR")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=_ferry_crew(ac_type="B777"))  # rated on the wrong type
    w = sim.check_ferry(state, "P1", "G-EAGE")
    assert any(x["code"] == "FERRY_NO_CAPTAIN" for x in w)
    assert any(x["code"] == "FERRY_NO_FO" for x in w)


def test_ferry_blocks_when_pilot_lacks_minimum_rest():
    flights = [_flight("EGW250", "G-EAGD", "A320", "07:00", 75, "P1", origin="MXP", destination="LHR")]
    crew = [_pilot("CP1", "CP", "A320", rest_hr=4), _pilot("FO1", "FO", "A320")]  # CP well under MIN_REST_HOME_HR
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=crew)
    w = sim.check_ferry(state, "P1", "G-EAGE")
    assert any(x["code"] == "FERRY_NO_CAPTAIN" for x in w)


def test_ferry_blocks_when_pilot_already_committed_elsewhere():
    flights = [
        _flight("EGW250", "G-EAGD", "A320", "07:00", 75, "P1", origin="MXP", destination="LHR"),
        # The only Captain is already flying something else that overlaps
        # the ferry's departure window.
        _flight("EGW500", "G-EAGA", "A320", "09:00", 60, "P5", status="scheduled"),
    ]
    flights[1]["assigned_crew_ids"] = ["CP1"]
    crew = [_pilot("CP1", "CP", "A320"), _pilot("FO1", "FO", "A320")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGA", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=crew, clock="2026-06-12T08:30:00+00:00")
    crew[0]["status"] = "on_duty"
    w = sim.check_ferry(state, "P1", "G-EAGE")
    assert any(x["code"] == "FERRY_NO_CAPTAIN" for x in w)


def test_ferry_crew_check_does_not_leak_a_flight_into_real_state():
    # check_ferry temporarily appends a candidate ferry flight to look up
    # crew legality — it must always be removed again, win or lose.
    flights = [_flight("EGW250", "G-EAGD", "A320", "07:00", 75, "P1", origin="MXP", destination="LHR")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=_ferry_crew())
    before = len(state["flights"])
    sim.check_ferry(state, "P1", "G-EAGE")
    assert len(state["flights"]) == before


# ---- LHR night curfew: no movements, schedule adjusts around it ----

def test_ferry_departure_delayed_past_curfew_at_lhr():
    # Idle at LHR at 23:30Z — dead in the curfew window (23:00-06:00Z).
    # Departure must be pushed to 06:00Z, not just fined.
    flights = [_flight("EGW250", "G-EAGD", "A320", "10:00", 75, "P1", origin="MXP", destination="LHR")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=_ferry_crew(), clock="2026-06-12T23:30:00+00:00")
    w = sim.check_ferry(state, "P1", "G-EAGE")
    curfew_warning = next((x for x in w if x["code"] == "FERRY_CURFEW_DELAY"), None)
    assert curfew_warning is not None
    assert curfew_warning["severity"] == "warning"  # adjusted, not blocked outright

    res = sim.ferry_spare_aircraft(state, "P1", "G-EAGE")
    assert res["applied"] is True
    std = sim.datetime.fromisoformat(res["ferry_flight"]["std"])
    assert std.hour == sim.CURFEW_END_HOUR and std.minute == 0
    assert std.date().isoformat() == "2026-06-13"  # pushed past midnight


def test_ferry_departure_not_delayed_outside_curfew():
    flights = [_flight("EGW250", "G-EAGD", "A320", "10:00", 75, "P1", origin="MXP", destination="LHR")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=_ferry_crew(), clock="2026-06-12T09:00:00+00:00")
    w = sim.check_ferry(state, "P1", "G-EAGE")
    assert not any(x["code"] == "FERRY_CURFEW_DELAY" for x in w)
    res = sim.ferry_spare_aircraft(state, "P1", "G-EAGE")
    std = sim.datetime.fromisoformat(res["ferry_flight"]["std"])
    assert std == sim.datetime.fromisoformat("2026-06-12T09:00:00+00:00")


def test_ferry_arrival_into_lhr_curfew_delays_departure_accordingly():
    # G-EAGE is at MXP; the stranded pairing needs it back at LHR. A normal
    # departure now would land at LHR well inside the curfew window.
    flights = [_flight("EGW250", "G-EAGE", "A320", "23:50", 75, "P9",
                        origin="MXP", destination="LHR", status="landed")]
    # The pairing needing rescue departs from LHR — G-EAGE is free after
    # its own (already-landed) sector, sitting at MXP.
    stranded = _flight("EGW300", "G-EAGD", "A320", "23:50", 75, "P1", origin="LHR", destination="CDG")
    flights.append(stranded)
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320"},
    ], crew=_ferry_crew(), clock="2026-06-12T22:00:00+00:00")
    res = sim.ferry_spare_aircraft(state, "P1", "G-EAGE")
    assert res["applied"] is True
    ferry = res["ferry_flight"]
    sta = sim.datetime.fromisoformat(ferry["sta"])
    assert not sim._in_curfew_window(sta)  # never lands at LHR mid-curfew


# ---- ferry_spare_aircraft: the actual dispatch, including crew ----

def test_ferry_creates_a_positioning_flight_and_moves_only_the_open_leg():
    flights = [
        _flight("EGW248", "G-EAGD", "A320", "04:00", 75, "P1",
                origin="LHR", destination="MXP", status="landed"),
        _flight("EGW250", "G-EAGD", "A320", "09:00", 75, "P1",
                origin="MXP", destination="LHR", status="delayed"),
    ]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=_ferry_crew(), clock="2026-06-12T08:00:00+00:00")

    res = sim.ferry_spare_aircraft(state, "P1", "G-EAGE")
    assert res["applied"] is True
    assert res["ferry_flight"] is not None
    ferry = res["ferry_flight"]
    assert ferry["origin"] == "LHR" and ferry["destination"] == "MXP"
    assert ferry["pax_count"] == 0
    assert ferry["aircraft_reg"] == "G-EAGE"
    assert ferry in state["flights"]

    # The ferry itself is crewed by exactly the minimum flight deck.
    assert set(ferry["assigned_crew_ids"]) == {"CP1", "FO1"}
    assert ferry["required_crew"]["CP"] == 1 and ferry["required_crew"]["FO"] == 1
    assert ferry["required_crew"]["SC"] == 0 and ferry["required_crew"]["CC"] == 0
    cp = next(c for c in state["crew"] if c["id"] == "CP1")
    fo = next(c for c in state["crew"] if c["id"] == "FO1")
    assert cp["status"] == "on_duty" and fo["status"] == "on_duty"

    # Already-flown leg keeps its real history; only the open leg moves.
    assert flights[0]["aircraft_reg"] == "G-EAGD"
    assert flights[1]["aircraft_reg"] == "G-EAGE"


def test_ferry_charges_a_real_cost_not_free():
    # An empty positioning flight burns fuel and crew time for zero revenue —
    # it must not be a free recovery lever when every other one isn't.
    flights = [
        _flight("EGW248", "G-EAGD", "A320", "04:00", 75, "P1",
                origin="LHR", destination="MXP", status="landed"),
        _flight("EGW250", "G-EAGD", "A320", "09:00", 75, "P1",
                origin="MXP", destination="LHR", status="delayed"),
    ]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=_ferry_crew(), clock="2026-06-12T08:00:00+00:00")

    res = sim.ferry_spare_aircraft(state, "P1", "G-EAGE")
    assert res["applied"] is True
    expected = sim.FERRY_DISPATCH_FEE_USD + res["ferry_flight"]["block_min"] * sim.FERRY_COST_PER_MIN_USD["A320"]
    assert res["cost_usd"] == expected
    assert res["cost_usd"] > 0
    assert state["kpis"]["cost_usd"] == expected

    # The open leg picks up delay for however long the ferry takes to land
    # (plus turnaround) — the existing reactionary-delay engine, not new math.
    assert flights[1]["reactionary_min"] > 0
    assert flights[1]["delay_min"] >= flights[1]["reactionary_min"]


def test_ferry_skips_creating_a_positioning_leg_when_already_in_place():
    # No repositioning needed at all here — no crew required either, since
    # there's no ferry flight to crew.
    flights = [_flight("EGW250", "G-EAGD", "A320", "09:00", 75, "P1", origin="LHR", destination="MXP")]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},  # idle at the hub == already at LHR
    ], clock="2026-06-12T08:00:00+00:00")
    res = sim.ferry_spare_aircraft(state, "P1", "G-EAGE")
    assert res["applied"] is True
    assert res["ferry_flight"] is None
    assert flights[0]["aircraft_reg"] == "G-EAGE"
    assert len(state["flights"]) == 1  # nothing extra got added


def test_ferry_infeasible_reg_is_rejected_without_mutation():
    flights = [
        _flight("EGW250", "G-EAGD", "A320", "07:00", 75, "P1", origin="MXP", destination="LHR"),
        _flight("EGW300", "G-EAGE", "A320", "07:30", 75, "P2", origin="LHR", destination="CDG"),
    ]
    state = _state(flights)
    res = sim.ferry_spare_aircraft(state, "P1", "G-EAGE")
    assert res["applied"] is False
    assert flights[0]["aircraft_reg"] == "G-EAGD"
    assert len(state["flights"]) == 2


# ---- Grading benchmark must consider ferry-eligible tails, not just cancel ----

def test_ferry_resolves_the_pending_incident_and_grades_it():
    flights = [
        _flight("EGW248", "G-EAGD", "A320", "04:00", 75, "P1",
                origin="LHR", destination="MXP", status="landed"),
        _flight("EGW250", "G-EAGD", "A320", "09:00", 75, "P1",
                origin="MXP", destination="LHR", status="delayed"),
    ]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=_ferry_crew(), clock="2026-06-12T08:00:00+00:00")
    inc = {
        "id": "INC-FERRY01", "type": "TECH", "severity": "major",
        "description": "Injected test defect", "raised_at": state["clock"],
        "flight_id": flights[1]["id"], "flight_callsign": flights[1]["callsign"],
        "status": "open", "resolution": None, "options": [], "escalated": False,
        "requires_aircraft_decision": True,
    }
    state["incidents"].append(inc)
    assert sim.is_clock_paused(state) is True

    res = sim.ferry_spare_aircraft(state, "P1", "G-EAGE")
    assert res["applied"] is True
    assert res["incident_resolved"] == inc["id"]
    assert res["decision_grade"]["player_choice"] == "G-EAGE"
    assert inc["status"] == "resolved"
    assert inc["resolution"] == "aircraft_control_ferry"
    assert "positioning flight" in inc["resolution_note"].lower()
    assert "cp1" in inc["resolution_note"].lower() or "CP1" in inc["resolution_note"]
    assert sim.is_clock_paused(state) is False


def test_best_decision_prefers_a_cheap_ferry_over_cancelling_a_full_flight():
    flights = [
        _flight("EGW248", "G-EAGD", "A320", "04:00", 75, "P1",
                origin="LHR", destination="MXP", status="landed"),
        _flight("EGW250", "G-EAGD", "A320", "09:00", 75, "P1",
                origin="MXP", destination="LHR", status="delayed"),
    ]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},  # idle at LHR — only a short hop from MXP
    ], crew=_ferry_crew(), clock="2026-06-12T08:00:00+00:00")
    best = sim._best_aircraft_decision(state, "P1")
    assert best["choice"] == "G-EAGE"


def test_best_decision_falls_back_to_cancel_when_no_ferry_crew_exists():
    # Same aircraft picture as above, but nobody's available to fly the
    # ferry — the benchmark must not pretend a ferry was viable.
    flights = [
        _flight("EGW248", "G-EAGD", "A320", "04:00", 75, "P1",
                origin="LHR", destination="MXP", status="landed"),
        _flight("EGW250", "G-EAGD", "A320", "09:00", 75, "P1",
                origin="MXP", destination="LHR", status="delayed"),
    ]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=[], clock="2026-06-12T08:00:00+00:00")  # no crew at all
    best = sim._best_aircraft_decision(state, "P1")
    assert best["choice"] == "cancel"


def test_preview_ferry_quotes_the_price_actually_charged():
    # The desk prices the ferry before committing; that quote has to be the
    # bill, or the preview is worse than useless.
    flights = [
        _flight("EGW248", "G-EAGD", "A320", "04:00", 75, "P1",
                origin="LHR", destination="MXP", status="landed"),
        _flight("EGW250", "G-EAGD", "A320", "09:00", 75, "P1",
                origin="MXP", destination="LHR", status="delayed"),
    ]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=_ferry_crew(), clock="2026-06-12T08:00:00+00:00")

    preview = sim.preview_ferry(state, "P1", "G-EAGE")
    assert preview["needs_ferry"] is True
    assert preview["cost_usd"] > 0
    assert preview["ferry_flight"]["origin"] == "LHR"
    assert preview["ferry_flight"]["destination"] == "MXP"
    # Preview is read-only — nothing billed, no positioning flight created yet.
    assert state["kpis"]["cost_usd"] == 0
    assert len(state["flights"]) == 2

    quoted = preview["cost_usd"]
    res = sim.ferry_spare_aircraft(state, "P1", "G-EAGE")
    assert res["applied"] is True
    assert res["cost_usd"] == quoted
    assert state["kpis"]["cost_usd"] == quoted


def test_preview_ferry_is_free_when_no_repositioning_needed():
    # The tail is already where the open leg starts — a plain reassignment
    # does the job, so there is no positioning flight and nothing to charge.
    flights = [
        _flight("EGW250", "G-EAGD", "A320", "09:00", 75, "P1",
                origin="LHR", destination="MXP", status="scheduled"),
    ]
    state = _state(flights, fleet=[
        {"reg": "G-EAGD", "type": "A320"},
        {"reg": "G-EAGE", "type": "A320", "spare": True},
    ], crew=_ferry_crew(), clock="2026-06-12T08:00:00+00:00")

    preview = sim.preview_ferry(state, "P1", "G-EAGE")
    assert preview["needs_ferry"] is False
    assert preview["cost_usd"] == 0
    assert preview["ferry_flight"] is None


def test_preview_ferry_prices_widebody_above_narrowbody():
    # Repositioning a B777 empty burns far more than an A320 over the same
    # sector — the lever's price has to reflect which metal you are moving.
    assert sim._ferry_cost("B777", 120) > sim._ferry_cost("A320", 120)
    assert sim._ferry_cost("A320", 120) == sim.FERRY_DISPATCH_FEE_USD + 120 * sim.FERRY_COST_PER_MIN_USD["A320"]
