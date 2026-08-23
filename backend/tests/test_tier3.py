"""Tier-3 realism-board items: the ORO.FTL.205 FDP tables, standby as a real
duty state, positioning (deadhead) as a real movement, and the problem monitor.

Pure engine tests, following the test_ferry.py pattern.
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
            origin="LHR", destination="CDG", delay_min=0, pax_count=150,
            crew_ids=None, fo=1):
    std_iso = f"2026-06-12T{std}:00+00:00"
    sta = sim._add_minutes_to_clock(std_iso, block_min)
    return {
        "id": f"FLT-{callsign}", "callsign": callsign,
        "origin": origin, "destination": destination,
        "std": std_iso, "sta": sta, "block_min": block_min,
        "aircraft_reg": reg, "aircraft_type": ac_type, "status": status,
        "delay_min": delay_min, "reactionary_min": 0, "pax_count": pax_count,
        "assigned_crew_ids": list(crew_ids or []),
        "required_crew": {"CP": 1, "FO": fo, "SC": 1, "CC": 3, "type_qual": ac_type},
        "pairing_id": pairing_id, "note": None,
    }


def _crew(cid, rank, name, status="available", **extra):
    c = {
        "id": cid, "rank": rank, "name": name, "base": "LHR",
        "qualifications": ["A320", "A350", "B777"], "status": status,
        "fdp_used_min": 0, "duty_7d_hr": 0, "block_28d_hr": 30.0,
        "rest_hr_since_duty": 14.0, "fatigue_score": 20, "days_since_off": 1,
        "days_off_planned": [], "last_duty_min": 0, "assigned_flight_id": None,
    }
    c.update(extra)
    return c


def _state(flights, crew=None, fleet=None, clock="2026-06-12T08:00:00+00:00"):
    return {
        "id": "GAME-T3", "flights": flights, "crew": crew or [],
        "fleet": fleet or [{"reg": "G-EAGA", "type": "A320"}],
        "incidents": [], "decisions_log": [], "cascade_log": [],
        "clock": clock, "day_start": "2026-06-12T04:00:00+00:00",
        "phase": "OPS", "day_number": 1,
        "kpis": {
            "otp_pct": 100.0, "legality_breaches": 0, "curfew_violations": 0,
            "compensation_usd": 0, "duty_of_care_usd": 0, "fatigue_index": 0,
            "cost_usd": 0, "pax_delay_min": 0, "pax_disrupted": 0,
            "reactionary_min": 0, "delay_cost_usd": 0,
            "completion_factor_pct": 100.0, "discretion_used_count": 0,
            "discretion_reports": 0, "score": 1000,
        },
    }


# --------------------------------------------------- ORO.FTL.205 FDP tables

def test_a_later_report_gets_a_shorter_duty():
    # Table 2 tapers from 13:00 down to 11:00 as the report slides into the
    # evening. A flat cap made an 05:00 start and a 17:00 start identical.
    morning = _flight("EGW100", "G-EAGA", "A320", "08:00", 75, "P1")
    evening = _flight("EGW200", "G-EAGA", "A320", "20:00", 75, "P2")
    cap_am, _ = sim._fdp_cap_for_flight(morning, sectors=2)
    cap_pm, _ = sim._fdp_cap_for_flight(evening, sectors=2)
    assert cap_am == 13 * 60
    assert cap_pm < cap_am


def test_more_sectors_cut_the_cap():
    f = _flight("EGW100", "G-EAGA", "A320", "08:00", 75, "P1")
    two, _ = sim._fdp_cap_for_flight(f, sectors=2)
    six, _ = sim._fdp_cap_for_flight(f, sectors=6)
    assert six < two
    # Sector count is now a scheduling decision rather than free.
    assert two - six == 120


def test_unacclimatised_crew_read_the_stricter_table():
    f = _flight("EGW100", "G-EAGA", "A320", "08:00", 75, "P1")
    ok, _ = sim._fdp_cap_for_flight(f, sectors=2, acclimatised=True)
    unknown, basis = sim._fdp_cap_for_flight(f, sectors=2, acclimatised=False)
    assert unknown == 11 * 60 < ok
    assert "Table 3" in basis


def test_a_crew_night_stopping_long_haul_is_unacclimatised():
    # Every long-haul station we serve is >=4h off UTC, so a night-stop there
    # leaves the crew in an unknown state on the way back.
    out = _flight("EGW900", "G-EAGN", "B777", "06:00", 410, "P9",
                  origin="LHR", destination="DXB", status="landed", crew_ids=["CP1"])
    back = _flight("EGW901", "G-EAGN", "B777", "20:00", 410, "P8",
                   origin="DXB", destination="LHR")
    crew = [_crew("CP1", "CP", "Larsen")]
    state = _state([out, back], crew=crew,
                   fleet=[{"reg": "G-EAGN", "type": "B777"}])
    assert sim._crew_acclimatised(state, crew[0], back) is False
    # A crew that stayed at base is acclimatised.
    home = _flight("EGW100", "G-EAGA", "A320", "08:00", 75, "P1")
    assert sim._crew_acclimatised(state, _crew("CP2", "CP", "Chen"), home) is True


def test_augmented_long_haul_still_uses_the_in_flight_rest_cap():
    # Table 2 is the cap for operations WITHOUT in-flight rest; augmented crew
    # with Class 1 bunks are governed separately and must not be cut by it.
    ulr = _flight("EGW950", "G-EAGP", "B777", "20:00", 770, "P9",
                  origin="LHR", destination="SIN", fo=2)
    cap, basis = sim._fdp_cap_for_flight(ulr, sectors=1)
    assert cap == 18 * 60
    assert "Class 1 bunks" in basis


# ----------------------------------------------------------------- standby

def test_home_standby_past_six_hours_erodes_the_following_duty():
    f = _flight("EGW100", "G-EAGA", "A320", "08:00", 75, "P1")
    fresh = _crew("CP1", "CP", "Larsen", status="standby",
                  standby_type=sim.STANDBY_HOME, standby_elapsed_hr=2.0)
    stale = _crew("CP2", "CP", "Chen", status="standby",
                  standby_type=sim.STANDBY_HOME, standby_elapsed_hr=9.0)
    assert sim._standby_fdp_reduction_min(fresh) == 0
    assert sim._standby_fdp_reduction_min(stale) == 180

    state = _state([f], crew=[stale])
    codes = [w for w in sim.check_assignment(state, "FLT-EGW100", "CP2")]
    basis = next((w["message"] for w in codes if w["code"] == "FDP_EXCEED"), "")
    # Whether or not it trips here, the reduction must be attributed when shown.
    assert basis == "" or "CS FTL.1.225" in basis


def test_airport_standby_does_not_erode_the_cap():
    # Airport standby counts as duty in full instead, which the duty accounting
    # handles — it must not ALSO be charged against the FDP cap.
    apt = _crew("CP1", "CP", "Larsen", status="standby",
                standby_type=sim.STANDBY_AIRPORT, standby_elapsed_hr=9.0)
    assert sim._standby_fdp_reduction_min(apt) == 0


def test_airport_standby_answers_faster_than_home_standby():
    apt = _crew("CP1", "CP", "Larsen", status="standby", standby_type=sim.STANDBY_AIRPORT)
    home = _crew("CP2", "CP", "Chen", status="standby", standby_type=sim.STANDBY_HOME)
    assert sim.standby_response_min(apt) < sim.standby_response_min(home)
    assert sim.standby_response_min(home) == 90


def test_a_callout_costs_the_notice_period_in_real_delay():
    # Calling a crew out used to be a ~2-minute penalty, which is why it
    # dominated every crew incident. Getting someone from home takes 90min.
    f = _flight("EGW100", "G-EAGA", "A320", "14:00", 75, "P1", crew_ids=[])
    standby = _crew("CP1", "CP", "Larsen", status="standby",
                    standby_type=sim.STANDBY_HOME, standby_elapsed_hr=1.0)
    state = _state([f], crew=[standby])
    inc = {
        "id": "INC-1", "type": "CREW_SICK", "severity": "minor",
        "flight_id": f["id"], "flight_callsign": f["callsign"], "status": "open",
        "resolution": None, "raised_at": state["clock"], "escalated": False,
        "options": sim._recovery_options_for(state, f, "CREW_SICK", "minor"),
    }
    state["incidents"].append(inc)
    res = sim.resolve_incident(state, "INC-1", "callout_standby")
    assert res["ok"] is True
    assert inc["callout_notice_min"] == 90
    assert f["delay_min"] == 90


# ------------------------------------------------------------- positioning

def test_positioning_needs_a_sector_that_actually_connects():
    # The old deadhead was `delay_min += 45` and was offered unconditionally.
    # With no inbound to ride, there is no positioning to be had.
    stranded = _flight("EGW300", "G-EAGA", "A320", "16:00", 75, "P3",
                       origin="MAD", destination="LHR")
    crew = [_crew("CP1", "CP", "Larsen")]
    state = _state([stranded], crew=crew)
    codes = [w["code"] for w in sim.check_deadhead(state, "FLT-EGW300")]
    assert "DH_NO_CONNECTION" in codes


def test_positioning_finds_the_inbound_and_prices_it():
    carrier = _flight("EGW200", "G-EAGB", "A320", "10:00", 90, "P2",
                      origin="LHR", destination="MAD")
    stranded = _flight("EGW300", "G-EAGA", "A320", "16:00", 90, "P3",
                       origin="MAD", destination="LHR")
    crew = [_crew("CP1", "CP", "Larsen")]
    state = _state([carrier, stranded], crew=crew)
    pv = sim.preview_deadhead(state, "FLT-EGW300")
    assert pv["needs_positioning"] is True
    assert pv["plan"]["carrier_callsign"] == "EGW200"
    assert pv["plan"]["from"] == "LHR" and pv["plan"]["to"] == "MAD"
    assert pv["cost_usd"] == sim.DEADHEAD_SEAT_USD + sim.DEADHEAD_HANDLING_USD


def test_positioning_moves_the_crew_and_charges_the_duty():
    carrier = _flight("EGW200", "G-EAGB", "A320", "10:00", 90, "P2",
                      origin="LHR", destination="MAD")
    stranded = _flight("EGW300", "G-EAGA", "A320", "16:00", 90, "P3",
                       origin="MAD", destination="LHR")
    crew = [_crew("CP1", "CP", "Larsen")]
    state = _state([carrier, stranded], crew=crew)
    inc = {
        "id": "INC-2", "type": "CREW_SICK", "severity": "minor",
        "flight_id": stranded["id"], "flight_callsign": "EGW300", "status": "open",
        "resolution": None, "raised_at": state["clock"], "escalated": False,
        "options": sim._recovery_options_for(state, stranded, "CREW_SICK", "minor"),
    }
    state["incidents"].append(inc)

    dh = next(o for o in inc["options"] if o["action"] == "deadhead")
    assert dh["feasible"] is True
    assert "EGW200" in dh["label"]

    res = sim.resolve_incident(state, "INC-2", "deadhead")
    assert res["ok"] is True
    # They actually moved, and ORO.FTL.215 charged the positioning as duty.
    assert crew[0]["positioning"][0]["to"] == "MAD"
    assert crew[0]["fdp_used_min"] == 90
    assert "CP1" in stranded["assigned_crew_ids"]


def test_a_positioned_crew_is_then_in_the_right_place():
    carrier = _flight("EGW200", "G-EAGB", "A320", "10:00", 90, "P2",
                      origin="LHR", destination="MAD")
    stranded = _flight("EGW300", "G-EAGA", "A320", "16:00", 90, "P3",
                       origin="MAD", destination="LHR")
    crew = [_crew("CP1", "CP", "Larsen")]
    state = _state([carrier, stranded], crew=crew)
    plan = sim._deadhead_plan(state, stranded, "CP1")
    crew[0]["positioning"] = [plan]
    codes = [w["code"] for w in sim.check_assignment(state, "FLT-EGW300", "CP1")]
    assert "CREW_WRONG_STATION" not in codes


# --------------------------------------------------------- problem monitor

def test_problem_monitor_reports_uncovered_flying():
    f = _flight("EGW100", "G-EAGA", "A320", "08:00", 75, "P1", crew_ids=[])
    state = _state([f], crew=[_crew("CP1", "CP", "Larsen")])
    codes = [w["code"] for w in sim.crew_irregularities(state)]
    assert "OPEN_SECTOR" in codes


def test_problem_monitor_reports_crew_out_of_position():
    f = _flight("EGW900", "G-EAGA", "A320", "14:00", 300, "P9",
                origin="JFK", destination="LHR", crew_ids=["CP1"])
    state = _state([f], crew=[_crew("CP1", "CP", "Larsen")])
    codes = [w["code"] for w in sim.crew_irregularities(state)]
    assert "CREW_OUT_OF_POSITION" in codes


def test_problem_monitor_warns_when_the_reserve_bank_runs_dry():
    f = _flight("EGW100", "G-EAGA", "A320", "08:00", 75, "P1", crew_ids=["CP1"])
    state = _state([f], crew=[_crew("CP1", "CP", "Larsen")])
    items = sim.crew_irregularities(state)
    assert any(w["code"] == "STANDBY_POOL_LOW" for w in items)


def test_problem_monitor_puts_blocking_items_first():
    f = _flight("EGW100", "G-EAGA", "A320", "08:00", 75, "P1", crew_ids=[])
    crew = [_crew("CP1", "CP", "Larsen", days_since_off=99)]
    state = _state([f], crew=crew)
    items = sim.crew_irregularities(state)
    severities = [w["severity"] for w in items]
    # Critical before warning — a live monitor is sorted by what stops you.
    assert severities == sorted(severities, key=lambda s: 0 if s == "critical" else 1)


def test_an_out_and_back_crew_is_in_position_for_their_own_return():
    # Both sectors share ONE pairing, which is how every short-haul day here is
    # built. Excluding the crew's own pairing from their position made every
    # return leg read as out of position — 36 false criticals on a live day.
    out = _flight("EGW113", "G-EAGA", "A320", "06:00", 125, "P1",
                  origin="LHR", destination="MXP", status="landed", crew_ids=["CP1"])
    back = _flight("EGW114", "G-EAGA", "A320", "10:00", 125, "P1",
                   origin="MXP", destination="LHR", crew_ids=["CP1"])
    state = _state([out, back], crew=[_crew("CP1", "CP", "Larsen")])
    codes = [w["code"] for w in sim.check_assignment(state, "FLT-EGW114", "CP1")]
    assert "CREW_WRONG_STATION" not in codes
    assert not any(w["code"] == "CREW_OUT_OF_POSITION"
                   for w in sim.crew_irregularities(state))


def test_a_late_inbound_is_delay_not_a_position_breach():
    # The crew land after the RETURN's scheduled departure because the outbound
    # ran late. That is knock-on delay, which the reactionary engine already
    # models — judging them against the timetable turned it into a fake breach.
    out = _flight("EGW113", "G-EAGA", "A320", "06:00", 125, "P1",
                  origin="LHR", destination="MXP", status="landed",
                  delay_min=180, crew_ids=["CP1"])
    back = _flight("EGW114", "G-EAGA", "A320", "09:00", 125, "P1",
                   origin="MXP", destination="LHR", delay_min=180, crew_ids=["CP1"])
    state = _state([out, back], crew=[_crew("CP1", "CP", "Larsen")])
    assert not any(w["code"] == "CREW_OUT_OF_POSITION"
                   for w in sim.crew_irregularities(state))


# ------------------------------------------- crew station across a rollover

def test_crew_stay_where_they_slept():
    # Position was derived only from TODAY'S flights and fell back to base, so
    # every crew the engine itself night-stopped down-route read as "out of
    # position" on day 2 — against the very returns it had pre-rostered them
    # onto. Measured at ~50 false criticals in every single game.
    crew = [_crew("CP1", "CP", "Larsen")]
    out = _flight("EGW900", "G-EAGN", "B777", "10:00", 770, "P9",
                  origin="LHR", destination="SIN", status="landed", crew_ids=["CP1"])
    state = _state([out], crew=crew, fleet=[{"reg": "G-EAGN", "type": "B777"}])
    crew[0]["station"] = sim._crew_end_of_day_station(state, crew[0])
    assert crew[0]["station"] == "SIN"

    # Tomorrow: yesterday's flights are gone and only the return exists. The
    # crew must still read as being at SIN.
    back = _flight("EGW901", "G-EAGN", "B777", "06:00", 770, "P8",
                   origin="SIN", destination="LHR", crew_ids=["CP1"])
    tomorrow = _state([back], crew=crew, fleet=[{"reg": "G-EAGN", "type": "B777"}])
    codes = [w["code"] for w in sim.check_assignment(tomorrow, "FLT-EGW901", "CP1")]
    assert "CREW_WRONG_STATION" not in codes
    assert not any(w["code"] == "CREW_OUT_OF_POSITION"
                   for w in sim.crew_irregularities(tomorrow))


def test_a_sector_still_airborne_at_rollover_still_moves_the_crew():
    # A 13-hour sector that has not landed by midnight still leaves its crew
    # in Singapore. Counting only "landed" missed most long-haul.
    crew = [_crew("CP1", "CP", "Larsen")]
    out = _flight("EGW900", "G-EAGN", "B777", "18:00", 770, "P9",
                  origin="LHR", destination="SIN", status="airborne", crew_ids=["CP1"])
    state = _state([out], crew=crew, fleet=[{"reg": "G-EAGN", "type": "B777"}])
    assert sim._crew_end_of_day_station(state, crew[0]) == "SIN"


def test_a_crew_who_never_left_is_still_at_base():
    crew = [_crew("CP1", "CP", "Larsen")]
    state = _state([], crew=crew)
    assert sim._crew_end_of_day_station(state, crew[0]) == "LHR"


def test_force_on_an_unrated_crew_applies_and_books_a_breach():
    # Current, documented behaviour: force is a commercial override that
    # applies and charges an 80-point legality breach, TYPE_QUAL included.
    # Flagged in the board log as a design question — a type rating is a
    # licensing fact under FCL.740, and discretion_available already refuses
    # to cover it — but this pins what the game does TODAY so a change is a
    # deliberate one rather than a silent drift.
    f = _flight("EGW900", "G-EAGN", "B777", "10:00", 700, "P9",
                origin="LHR", destination="JFK")
    f["required_crew"]["type_qual"] = "B777"
    c = _crew("CP1", "CP", "Larsen")
    c["qualifications"] = ["A320"]
    state = _state([f], crew=[c], fleet=[{"reg": "G-EAGN", "type": "B777"}])

    assert sim.assign_crew(state, "FLT-EGW900", "CP1")["applied"] is False
    res = sim.assign_crew(state, "FLT-EGW900", "CP1", force=True)
    assert res["applied"] is True
    assert state["kpis"]["legality_breaches"] >= 1

    # Discretion, unlike force, must never reach it.
    assert sim.discretion_available(state, "FLT-EGW900", "CP1")["available"] is False


def test_force_still_covers_a_genuine_commercial_call():
    # Rest is a judgement a controller may take and pay for — force must still
    # work there, or the override becomes useless.
    f = _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1")
    c = _crew("CP1", "CP", "Larsen", rest_hr_since_duty=4.0)
    state = _state([f], crew=[c])
    codes = [w["code"] for w in sim.check_assignment(state, "FLT-EGW100", "CP1")]
    assert "MIN_REST" in codes
    res = sim.assign_crew(state, "FLT-EGW100", "CP1", force=True)
    assert res["applied"] is True
    assert state["kpis"]["legality_breaches"] >= 1


# ------------------------------------------------- dead-end grounding pause

def test_a_grounding_whose_rotation_is_gone_stops_freezing_the_clock():
    # A pairing can be cancelled from the incident queue while the pause is
    # open on a sibling sector. The rotation is then gone, Aircraft Control has
    # nothing to offer, and the clock stayed frozen forever — measured at 20%
    # of clock-pausing groundings.
    f = _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1")
    state = _state([f])
    state["incidents"].append({
        "id": "INC-9", "type": "TECH", "severity": "major", "status": "open",
        "flight_id": f["id"], "flight_callsign": "EGW100", "pairing_id": "P1",
        "raised_at": state["clock"], "escalated": False, "options": [],
        "requires_aircraft_decision": True, "resolution": None,
    })
    assert sim.is_clock_paused(state) is True

    # The rotation goes away by another route.
    f["status"] = "cancelled"
    assert sim.is_clock_paused(state) is False

    released = sim.release_superseded_aircraft_decisions(state)
    assert [i["id"] for i in released] == ["INC-9"]
    inc = state["incidents"][0]
    assert inc["status"] == "resolved"
    assert inc["resolution"] == "superseded"
    # Resolved, not deleted — it still happened and the debrief should say so.
    assert "EGW100" in inc["resolution_note"]


def test_a_live_grounding_still_freezes_the_clock():
    f = _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1")
    state = _state([f])
    state["incidents"].append({
        "id": "INC-9", "type": "TECH", "severity": "major", "status": "open",
        "flight_id": f["id"], "flight_callsign": "EGW100", "pairing_id": "P1",
        "raised_at": state["clock"], "escalated": False, "options": [],
        "requires_aircraft_decision": True, "resolution": None,
    })
    assert sim.is_clock_paused(state) is True
    assert sim.release_superseded_aircraft_decisions(state) == []
    assert sim.is_clock_paused(state) is True


# ----------------------------------------------- irregularity suppression

def test_a_condition_already_on_a_card_is_not_also_a_condition():
    # The same uncovered sector rendering as both an incident and a monitor
    # line is the canonical nuisance-alarm pattern.
    f = _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1", crew_ids=[])
    state = _state([f], crew=[_crew("CP1", "CP", "Larsen")])
    assert any(w["code"] == "OPEN_SECTOR" for w in sim.crew_irregularities(state))

    state["incidents"].append({
        "id": "INC-1", "type": "CREW_SICK", "severity": "minor", "status": "open",
        "flight_id": f["id"], "flight_callsign": "EGW100", "pairing_id": "P1",
        "raised_at": state["clock"], "escalated": False, "options": [],
        "resolution": None,
    })
    full = sim.crew_irregularities_full(state)
    assert not any(w["code"] == "OPEN_SECTOR" for w in full["irregularities"])
    # Held back, not hidden.
    assert any(w["code"] == "OPEN_SECTOR" for w in full["suppressed"])


def test_severity_grades_off_time_left_not_a_flat_critical():
    # An uncovered sector nine hours out is a task; the same sector twenty
    # minutes out is blocking. Three of five codes used to be flat critical,
    # so the BLOCKING count carried no information.
    far = _flight("EGW100", "G-EAGA", "A320", "20:00", 75, "P1", crew_ids=[])
    near = _flight("EGW200", "G-EAGB", "A320", "08:30", 75, "P2", crew_ids=[])
    state = _state([far, near], crew=[_crew("CP1", "CP", "Larsen")])
    by_flight = {w["flight_id"]: w for w in sim.crew_irregularities(state)
                 if w["code"] == "OPEN_SECTOR"}
    assert by_flight["FLT-EGW200"]["severity"] == "critical"
    assert by_flight["FLT-EGW100"]["severity"] == "advisory"
