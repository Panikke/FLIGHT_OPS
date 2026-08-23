"""Unit tests for the "reset to zero" recovery lever: pre-emptively
cancelling a whole block of pairings in one deliberate move to resync the
fleet, rather than reacting incident-by-incident (the real Southwest
Dec 2022 IROPS tactic — see docs/research/Aircraft-Fleet-Management-Research.md §5).

Pure engine tests (no server), following the test_ferry.py pattern.
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
            origin="LHR", destination="CDG", reactionary_min=0, pax_count=150):
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
        "delay_min": reactionary_min,
        "reactionary_min": reactionary_min,
        "pax_count": pax_count,
        "assigned_crew_ids": [],
        "required_crew": {"CP": 1, "FO": 1, "SC": 1, "CC": 4, "type_qual": ac_type},
        "pairing_id": pairing_id,
        "note": "",
    }


def _state(flights, fleet=None, crew=None, clock="2026-06-12T09:00:00+00:00"):
    return {
        "flights": flights,
        "crew": crew if crew is not None else [],
        "fleet": fleet or [
            {"reg": "G-EAGA", "type": "A320"},
            {"reg": "G-EAGB", "type": "A320"},
        ],
        "phase": "OPS",
        "clock": clock,
        "incidents": [],
        "decisions_log": [],
        "kpis": {
            "otp_pct": 100.0, "legality_breaches": 0, "cost_usd": 0,
            "pax_disrupted": 0, "pax_delay_min": 0, "fatigue_index": 0, "score": 1000,
        },
    }


# ---- check_reset_to_zero: feasibility ----

def test_rejects_empty_selection():
    state = _state([])
    w = sim.check_reset_to_zero(state, [])
    assert any(x["code"] == "RTZ_EMPTY" for x in w)


def test_rejects_unknown_pairing():
    state = _state([_flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1")])
    w = sim.check_reset_to_zero(state, ["NOPE"])
    assert any(x["code"] == "REF_NOT_FOUND" for x in w)


def test_rejects_pairing_with_nothing_left_to_cancel():
    state = _state([_flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1", status="landed")])
    w = sim.check_reset_to_zero(state, ["P1"])
    assert any(x["code"] == "RTZ_NOTHING_TO_CANCEL" for x in w)


def test_accepts_a_normal_scheduled_pairing():
    state = _state([_flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1")])
    w = sim.check_reset_to_zero(state, ["P1"])
    assert w == []


# ---- reset_to_zero: the actual action ----

def test_cancels_every_selected_pairing_and_charges_cost():
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1", pax_count=150),
        _flight("EGW200", "G-EAGB", "A320", "11:00", 130, "P2", pax_count=170),
    ]
    state = _state(flights)
    res = sim.reset_to_zero(state, ["P1", "P2"])
    assert res["applied"] is True
    assert flights[0]["status"] == "cancelled"
    assert flights[1]["status"] == "cancelled"
    expected_cost = 15000 * 2 + (150 + 170) * 280
    # Cancelling under 14 days' notice owes Art. 7 compensation as well as the
    # cancellation cost — it is not a way to escape what the pax were owed.
    expected_comp = sum(sim.COMP_SHORT_HAUL_USD * f["pax_count"] for f in flights)
    # Stranded passengers are also owed Art. 9 care — meals and a hotel.
    care_rate = sim.CARE_MEAL_USD_PER_PAX + sim.CARE_HOTEL_USD_PER_PAX
    expected_care = sum(care_rate * f["pax_count"] for f in flights)
    assert res["cancellation_cost_usd"] == expected_cost
    assert res["compensation_usd"] == expected_comp
    assert res["duty_of_care_usd"] == expected_care
    assert res["cost_usd"] == expected_cost + expected_comp + expected_care
    assert state["kpis"]["cost_usd"] == expected_cost + expected_comp + expected_care
    assert state["kpis"]["compensation_usd"] == expected_comp
    assert state["kpis"]["duty_of_care_usd"] == expected_care
    assert state["kpis"]["pax_disrupted"] == 150 + 170


def test_only_cancels_the_remaining_leg_of_a_partially_flown_pairing():
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "04:00", 75, "P1", status="landed", pax_count=150),
        _flight("EGW102", "G-EAGA", "A320", "09:00", 75, "P1", status="delayed", pax_count=150),
    ]
    state = _state(flights)
    res = sim.reset_to_zero(state, ["P1"])
    assert res["applied"] is True
    assert flights[0]["status"] == "landed"       # already-flown leg untouched
    assert flights[1]["status"] == "cancelled"    # only the open leg cancelled
    assert res["cancellation_cost_usd"] == 15000 * 1 + 150 * 280
    assert res["compensation_usd"] == sim.COMP_SHORT_HAUL_USD * 150


def test_releases_crew_back_to_the_pool():
    flight = _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1")
    flight["assigned_crew_ids"] = ["CP1"]
    crew = [{"id": "CP1", "status": "on_duty", "assigned_flight_id": "FLT-EGW100"}]
    state = _state([flight], crew=crew)
    sim.reset_to_zero(state, ["P1"])
    assert crew[0]["status"] == "available"
    assert crew[0]["assigned_flight_id"] is None


def test_blocked_selection_charges_nothing_and_mutates_nothing():
    flight = _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1", status="landed")
    state = _state([flight])
    res = sim.reset_to_zero(state, ["P1"])
    assert res["applied"] is False
    assert flight["status"] == "landed"
    assert state["kpis"]["cost_usd"] == 0


def test_resyncs_reactionary_delay_across_the_whole_network_not_just_cancelled_pairings():
    # G-EAGA flies P1 then P3 back-to-back. P1 is stuck with pre-existing
    # reactionary delay that's pushing its departure late enough to also
    # delay P3 (the same tail's next rotation). Cancelling P1 should let
    # P3 depart on time again — the whole point of resyncing the network,
    # not just wiping the delay off the cancelled pairing itself.
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1", reactionary_min=200),
        _flight("EGW300", "G-EAGA", "A320", "11:30", 75, "P3"),
    ]
    state = _state(flights)
    sim.propagate_reactionary_delays(state)
    knock_on = flights[1]["reactionary_min"]
    assert knock_on > 0, "P3 should be waiting on the late tail before we start"

    res = sim.reset_to_zero(state, ["P1"])
    assert res["applied"] is True
    assert flights[0]["status"] == "cancelled"
    assert flights[1].get("reactionary_min", 0) == 0
    assert flights[1]["status"] == "scheduled"
    # Only THIRD-PARTY relief counts. The cancelled sector's own 200min is the
    # price of the decision, not a benefit of it.
    assert res["reactionary_avoided_min"] == knock_on
    assert res["sectors_relieved"] == 1


# ---- preview_reset_to_zero: read-only what-if ----

def test_preview_does_not_mutate_real_state():
    flights = [_flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1", pax_count=150)]
    state = _state(flights)
    preview = sim.preview_reset_to_zero(state, ["P1"])
    assert flights[0]["status"] == "scheduled"
    assert state["kpis"]["cost_usd"] == 0
    assert preview["cancellation_cost_usd"] == 15000 + 150 * 280
    assert preview["compensation_usd"] == sim.COMP_SHORT_HAUL_USD * 150
    assert preview["duty_of_care_usd"] == (
        sim.CARE_MEAL_USD_PER_PAX + sim.CARE_HOTEL_USD_PER_PAX) * 150
    assert preview["cost_usd"] == (
        preview["cancellation_cost_usd"] + preview["compensation_usd"]
        + preview["duty_of_care_usd"])
    assert preview["cancel_sectors"] == 1
    assert preview["cancel_pax"] == 150


def test_preview_reports_reactionary_minutes_avoided():
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1", reactionary_min=200),
        _flight("EGW300", "G-EAGA", "A320", "11:30", 75, "P3"),
    ]
    state = _state(flights)
    sim.propagate_reactionary_delays(state)
    knock_on = flights[1]["reactionary_min"]
    preview = sim.preview_reset_to_zero(state, ["P1"])
    assert preview["network_reactionary_before_min"] == knock_on
    assert preview["network_reactionary_after_min"] == 0
    assert preview["reactionary_avoided_min"] == knock_on
    assert preview["sectors_relieved"] == 1
    # Read-only: real state untouched.
    assert flights[0]["status"] == "scheduled"
    assert flights[0]["reactionary_min"] == 200


def test_reset_takes_no_credit_for_deleting_its_own_delay():
    # A pairing carrying 200min of its own knock-on, with nothing downstream
    # of it. Cancelling wipes that 200min — but only because the flights are
    # gone. Reporting it as "avoided" is the airline congratulating itself for
    # deleting the evidence, and previously that was 100% of the number shown
    # against a six-figure cost.
    flights = [
        _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1", reactionary_min=200),
        _flight("EGW300", "G-EAGB", "A320", "11:30", 75, "P3"),   # different tail
    ]
    state = _state(flights)
    sim.propagate_reactionary_delays(state)

    preview = sim.preview_reset_to_zero(state, ["P1"])
    assert preview["reactionary_avoided_min"] == 0
    assert preview["sectors_relieved"] == 0

    res = sim.reset_to_zero(state, ["P1"])
    assert res["reactionary_avoided_min"] == 0
    assert res["sectors_relieved"] == 0


def test_weather_exempts_compensation_but_never_the_duty_of_care():
    # Extraordinary circumstances defeat Art. 7 whether the flight is delayed
    # or cancelled. They do NOT defeat Art. 9 care — McDonagh v Ryanair
    # (C-12/11). A weather day still has to feed and house the passengers.
    flights = [_flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1", pax_count=150)]
    flights[0]["comp_exempt"] = True
    state = _state(flights)
    res = sim.reset_to_zero(state, ["P1"])
    assert res["compensation_usd"] == 0
    assert res["duty_of_care_usd"] == (
        sim.CARE_MEAL_USD_PER_PAX + sim.CARE_HOTEL_USD_PER_PAX) * 150
    assert res["cost_usd"] == res["cancellation_cost_usd"] + res["duty_of_care_usd"]
