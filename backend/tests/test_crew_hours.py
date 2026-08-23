"""Tests for the Tier-1 realism pass: delay consuming crew FDP, reactionary
delay being priced into the score, and the cascade attribution ledger.

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
            origin="LHR", destination="CDG", delay_min=0, pax_count=150, crew_ids=None):
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
        "delay_min": delay_min,
        "reactionary_min": 0,
        "pax_count": pax_count,
        "assigned_crew_ids": list(crew_ids or []),
        "required_crew": {"CP": 1, "FO": 1, "SC": 1, "CC": 4, "type_qual": ac_type},
        "pairing_id": pairing_id,
        "note": "",
    }


def _crew(cid, rank, name, fdp_used=0, status="on_duty"):
    return {
        "id": cid, "name": name, "rank": rank, "base": "LHR",
        "qualifications": ["A320", "A350", "B777"], "status": status,
        "fatigue_score": 20, "days_since_off": 1, "block_28d_hr": 30.0,
        "days_off_planned": [], "last_duty_min": 0,
        "fdp_used_min": fdp_used, "duty_7d_hr": 0, "duty_28d_hr": 0,
        "rest_hr_since_duty": 14, "consecutive_duty_days": 1,
        "fatigue": 20, "assigned_flight_id": None, "days_off_last_7": 2,
    }


def _state(flights, crew=None, clock="2026-06-12T09:00:00+00:00"):
    return {
        "flights": flights,
        "crew": crew if crew is not None else [],
        "fleet": [{"reg": "G-EAGA", "type": "A320"}, {"reg": "G-EAGB", "type": "A320"}],
        "phase": "OPS",
        "clock": clock,
        "incidents": [],
        "decisions_log": [],
        "cascade_log": [],
        "kpis": {
            "otp_pct": 100.0, "legality_breaches": 0, "curfew_violations": 0,
            "compensation_usd": 0, "fatigue_index": 0, "cost_usd": 0,
            "pax_delay_min": 0, "pax_disrupted": 0, "reactionary_min": 0,
            "delay_cost_usd": 0, "completion_factor_pct": 100.0, "score": 1000,
        },
    }


# ---------------------------------------------------------------- delay to FDP

def test_delay_is_counted_as_flight_duty_period():
    # An FDP runs report-to-final-on-blocks, so ground delay is duty burned.
    # The same pairing must project a longer FDP once it slips.
    clean = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1"),
             _flight("EGW201", "G-EAGA", "A320", "12:00", 90, "P1",
                     origin="CDG", destination="LHR")]
    state = _state(clean)
    total_clean, sched, delay, sectors = sim._pairing_fdp_min(state, clean[0])
    assert delay == 0 and total_clean == sched and sectors == 2

    clean[1]["delay_min"] = 150
    total_late, sched_late, delay_late, _ = sim._pairing_fdp_min(state, clean[0])
    assert sched_late == sched          # the schedule did not change
    assert delay_late == 150
    assert total_late == total_clean + 150


def test_a_delayed_pairing_can_make_a_previously_legal_crew_illegal():
    # The crew was legal at report. Nothing about the roster changed, only the
    # operation slipped, and that alone must be able to break the duty.
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 300, "P1",
                       origin="LHR", destination="ATH", crew_ids=["CP1"]),
               _flight("EGW201", "G-EAGA", "A320", "16:00", 300, "P1",
                       origin="ATH", destination="LHR", crew_ids=["CP1"])]
    crew = [_crew("CP1", "CP", "Larsen")]
    state = _state(flights, crew=crew)

    assert sim.check_crew_hours(state, flights[0]) == []

    flights[1]["delay_min"] = 240
    warnings = sim.check_crew_hours(state, flights[0])
    assert len(warnings) == 1
    assert warnings[0]["code"] == "FDP_TIMEOUT"
    assert warnings[0]["severity"] == "critical"
    assert warnings[0]["crew_id"] == "CP1"
    assert warnings[0]["over_by_min"] > 0
    assert "ORO.FTL.205" in warnings[0]["rule_ref"]


def test_duty_clock_reports_slack_and_latest_off_blocks():
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1", crew_ids=["CP1"]),
               _flight("EGW201", "G-EAGA", "A320", "12:00", 90, "P1",
                       origin="CDG", destination="LHR", crew_ids=["CP1"])]
    state = _state(flights, crew=[_crew("CP1", "CP", "Larsen")])

    clock = sim.crew_duty_clock(state, "CP1")
    assert clock["on_duty"] is True
    assert clock["legal"] is True
    assert clock["slack_min"] > 0
    # Report is 08:00Z (60 min before the 09:00 STD); a 13h cap puts the
    # latest off-blocks at 08:00 + 13:00 - 30min post-flight = 20:30Z.
    assert clock["latest_off_blocks"].startswith("2026-06-12T20:30")

    # Scheduled FDP for this pairing is 5h30 against a 13h cap, so it takes
    # more than 7h30 of slippage to actually break the duty.
    flights[1]["delay_min"] = 300
    slipping = sim.crew_duty_clock(state, "CP1")
    assert slipping["delay_min"] == 300
    assert slipping["slack_min"] == clock["slack_min"] - 300
    assert slipping["legal"] is True

    flights[1]["delay_min"] = 480
    late = sim.crew_duty_clock(state, "CP1")
    assert late["slack_min"] < 0
    assert late["legal"] is False


def test_crew_with_no_assignment_has_no_running_clock():
    state = _state([], crew=[_crew("CP9", "CP", "Idle", status="standby")])
    clock = sim.crew_duty_clock(state, "CP9")
    assert clock["on_duty"] is False
    assert clock["latest_off_blocks"] is None
    assert sim.crew_duty_clock(state, "NOPE") is None


def test_crew_hours_check_ignores_flights_that_are_done():
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 300, "P1",
                       status="landed", delay_min=400, crew_ids=["CP1"])]
    state = _state(flights, crew=[_crew("CP1", "CP", "Larsen")])
    assert sim.check_crew_hours(state, flights[0]) == []


# -------------------------------------------------------- reactionary pricing

def test_reactionary_minutes_cost_money_and_score():
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1")]
    state = _state(flights)
    sim._recompute_kpis(state)
    assert state["kpis"]["reactionary_min"] == 0
    assert state["kpis"]["delay_cost_usd"] == 0
    clean_score = state["kpis"]["score"]

    flights[0]["reactionary_min"] = 120
    sim._recompute_kpis(state)
    assert state["kpis"]["reactionary_min"] == 120
    assert state["kpis"]["delay_cost_usd"] == 120 * sim.DELAY_COST_PER_MIN_USD
    # Knock-on minutes must actually cost the player something.
    assert state["kpis"]["score"] < clean_score


def test_otp_measures_operated_flights_and_cancelling_hits_completion_factor():
    # Cancelling must not be punished twice through a single number: it leaves
    # OTP alone (a cancelled sector is not a late sector) and shows up in the
    # completion factor instead.
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1"),
               _flight("EGW201", "G-EAGA", "A320", "12:00", 90, "P2"),
               _flight("EGW202", "G-EAGB", "A320", "15:00", 90, "P3"),
               _flight("EGW203", "G-EAGB", "A320", "18:00", 90, "P4")]
    state = _state(flights)
    sim._recompute_kpis(state)
    assert state["kpis"]["otp_pct"] == 100.0
    assert state["kpis"]["completion_factor_pct"] == 100.0

    flights[0]["status"] = "cancelled"
    sim._recompute_kpis(state)
    assert state["kpis"]["otp_pct"] == 100.0          # the other three are still on time
    assert state["kpis"]["completion_factor_pct"] == 75.0


# ------------------------------------------------------------- cascade ledger

def test_cascade_ledger_records_which_inbound_caused_which_delay():
    # Two sectors on one tail: the first runs 200 min late, so the second
    # cannot depart on time. The ledger has to name the culprit, not just
    # record the victim's minute count.
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1", delay_min=200),
               _flight("EGW201", "G-EAGA", "A320", "12:00", 90, "P2",
                       origin="CDG", destination="LHR")]
    state = _state(flights)

    affected = sim._log_cascade(state, sim.propagate_reactionary_delays(state), "tick")
    assert affected, "the second sector should have picked up knock-on delay"

    log = state["cascade_log"]
    assert len(log) == len(affected)
    edge = next(e for e in log if e["callsign"] == "EGW201")
    assert edge["inbound_callsign"] == "EGW200"
    assert edge["added_min"] > 0
    assert edge["trigger"] == "tick"
    assert edge["ts"] == state["clock"]


def test_cascade_ledger_carries_the_triggering_decision():
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1", delay_min=200),
               _flight("EGW201", "G-EAGA", "A320", "12:00", 90, "P2",
                       origin="CDG", destination="LHR")]
    state = _state(flights)
    sim._log_cascade(state, sim.propagate_reactionary_delays(state),
                     "incident_delay", "INC-ABC123")
    assert state["cascade_log"][0]["trigger"] == "incident_delay"
    assert state["cascade_log"][0]["trigger_id"] == "INC-ABC123"


def test_previews_never_write_to_the_cascade_ledger():
    # preview_* runs propagation on scratch copies; a what-if the player never
    # committed to must not appear in the record of what actually happened.
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1", delay_min=200),
               _flight("EGW201", "G-EAGA", "A320", "12:00", 90, "P1",
                       origin="CDG", destination="LHR")]
    state = _state(flights)
    sim.preview_reset_to_zero(state, ["P1"])
    assert state["cascade_log"] == []


def test_duty_clock_does_not_double_count_sectors_already_flown():
    # fdp_used_min accrues as each sector lands, and _pairing_fdp_min spans the
    # whole pairing including those sectors. Adding them together would charge
    # the flown legs twice and report a legal crew as hours-busted.
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1",
                       status="landed", crew_ids=["CP1"]),
               _flight("EGW201", "G-EAGA", "A320", "12:00", 90, "P1",
                       origin="CDG", destination="LHR", crew_ids=["CP1"])]
    # The outbound has landed, so its 90 min of block is already on the crew.
    state = _state(flights, crew=[_crew("CP1", "CP", "Larsen", fdp_used=90)])

    clock = sim.crew_duty_clock(state, "CP1")
    assert clock["on_duty"] is True
    assert clock["prior_duty_min"] == 0          # nothing from any OTHER pairing
    assert clock["fdp_projected_min"] == clock["fdp_scheduled_min"]
    assert clock["legal"] is True
    assert sim.check_crew_hours(state, flights[1]) == []


def test_duty_clock_still_carries_duty_from_an_earlier_pairing():
    flights = [_flight("EGW300", "G-EAGA", "A320", "14:00", 90, "P9", crew_ids=["CP1"])]
    # 400 min of duty already flown today on a different pairing.
    state = _state(flights, crew=[_crew("CP1", "CP", "Larsen", fdp_used=400)])
    clock = sim.crew_duty_clock(state, "CP1")
    assert clock["prior_duty_min"] == 400
    assert clock["fdp_projected_min"] == 400 + clock["fdp_scheduled_min"]


def test_a_fully_landed_duty_is_no_longer_running():
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1",
                       status="landed", crew_ids=["CP1"])]
    state = _state(flights, crew=[_crew("CP1", "CP", "Larsen", fdp_used=90)])
    assert sim.crew_duty_clock(state, "CP1")["on_duty"] is False


# ------------------------------------------------------- Art. 9 duty of care

def test_weather_delay_is_not_economically_free():
    # Weather exempts compensation but not care. Without this, accepting delay
    # is strictly dominant whenever the cause is weather or ATC — backwards
    # from the real calculus.
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1",
                       delay_min=200, pax_count=150)]
    flights[0]["comp_exempt"] = True
    state = _state(flights)

    comp = sim._maybe_charge_compensation(state, flights[0])
    care = sim._maybe_charge_duty_of_care(state, flights[0])
    assert comp is None                       # extraordinary circumstances
    assert care is not None                   # care is still owed
    assert care["overnight"] is False         # 200min: meals, no hotel yet
    assert state["kpis"]["duty_of_care_usd"] == 150 * sim.CARE_MEAL_USD_PER_PAX
    assert state["kpis"]["cost_usd"] == state["kpis"]["duty_of_care_usd"]


def test_a_long_enough_delay_puts_passengers_in_a_hotel():
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1",
                       delay_min=500, pax_count=100)]
    state = _state(flights)
    care = sim._maybe_charge_duty_of_care(state, flights[0])
    assert care["overnight"] is True
    assert state["kpis"]["duty_of_care_usd"] == 100 * (
        sim.CARE_MEAL_USD_PER_PAX + sim.CARE_HOTEL_USD_PER_PAX)


def test_care_thresholds_are_banded_by_sector_length():
    # A 90-minute hop owes care sooner than a long-haul sector does.
    short = _flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1", delay_min=130)
    long_haul = _flight("EGW900", "G-EAGN", "B777", "09:00", 700, "P9", delay_min=130)
    state = _state([short, long_haul])
    assert sim._maybe_charge_duty_of_care(state, short) is not None
    assert sim._maybe_charge_duty_of_care(state, long_haul) is None


def test_care_is_charged_once_per_flight():
    flights = [_flight("EGW200", "G-EAGA", "A320", "09:00", 90, "P1",
                       delay_min=200, pax_count=150)]
    state = _state(flights)
    assert sim._maybe_charge_duty_of_care(state, flights[0]) is not None
    assert sim._maybe_charge_duty_of_care(state, flights[0]) is None
    assert state["kpis"]["duty_of_care_usd"] == 150 * sim.CARE_MEAL_USD_PER_PAX


# ------------------------------------------------------- crew position

def test_crew_cannot_operate_a_departure_they_are_not_at():
    # The crew-side half of AC_WRONG_STATION. An LHR-based crew with no earlier
    # flying is at LHR, so a JFK departure is not theirs to operate.
    flights = [_flight("EGW900", "G-EAGA", "A320", "14:00", 300, "P9",
                       origin="JFK", destination="LHR")]
    state = _state(flights, crew=[_crew("CP1", "CP", "Larsen", status="available")])
    codes = [w["code"] for w in sim.check_assignment(state, "FLT-EGW900", "CP1")]
    assert "CREW_WRONG_STATION" in codes


def test_crew_who_flew_out_are_in_position_for_the_return():
    # Having operated LHR->JFK, the same crew ARE at JFK for the return — and
    # crucially this holds when both sectors share ONE pairing, which is how
    # every out-and-back in this sim is built. Using two pairing ids here
    # dodged the real case and let a bug through: the crew's own outbound was
    # being excluded from their position, so every return leg read as out of
    # position.
    out = _flight("EGW899", "G-EAGA", "A320", "06:00", 300, "P9",
                  origin="LHR", destination="JFK", status="landed", crew_ids=["CP1"])
    back = _flight("EGW900", "G-EAGA", "A320", "14:00", 300, "P9",
                   origin="JFK", destination="LHR")
    state = _state([out, back], crew=[_crew("CP1", "CP", "Larsen", status="available")])
    codes = [w["code"] for w in sim.check_assignment(state, "FLT-EGW900", "CP1")]
    assert "CREW_WRONG_STATION" not in codes


def test_crew_position_is_overridable_unlike_an_aircraft():
    # A crew CAN be positioned to the departure station; a tail cannot be
    # teleported. So this one is a commercial call, not a physical wall.
    flights = [_flight("EGW900", "G-EAGA", "A320", "14:00", 300, "P9",
                       origin="JFK", destination="LHR")]
    state = _state(flights, crew=[_crew("CP1", "CP", "Larsen", status="available")])
    res = sim.assign_crew(state, "FLT-EGW900", "CP1", force=True)
    assert res["ok"] is True
    assert "CP1" in flights[0]["assigned_crew_ids"]


# ------------------------------------------------- commander's discretion

def _timed_out_state():
    """A pairing delayed far enough that its crew busts FDP."""
    out = _flight("EGW100", "G-EAGA", "A320", "06:00", 300, "P1",
                  origin="LHR", destination="CDG", crew_ids=["CP1"])
    back = _flight("EGW101", "G-EAGA", "A320", "13:00", 300, "P1",
                   origin="CDG", destination="LHR", crew_ids=["CP1"], delay_min=90)
    crew = [_crew("CP1", "CP", "Larsen", status="available")]
    return _state([out, back], crew=crew), out, back


def test_discretion_covers_an_fdp_overrun_within_its_cap():
    state, out, back = _timed_out_state()
    disc = sim.discretion_available(state, "FLT-EGW100", "CP1")
    assert disc["available"] is True
    assert 0 < disc["overrun_min"] <= sim.DISCRETION_MAX_MIN


def test_discretion_is_legal_and_books_no_breach_unlike_force():
    state, out, back = _timed_out_state()
    res = sim.assign_crew(state, "FLT-EGW100", "CP1", discretion=True)
    assert res["ok"] is True and res["applied"] is True
    # The whole point: this is a licensed captain's call, not a rule broken.
    assert state["kpis"]["legality_breaches"] == 0
    assert state["kpis"]["discretion_used_count"] == 1


def test_discretion_past_the_reporting_threshold_files_a_report():
    state, out, back = _timed_out_state()
    back["delay_min"] = 130         # overrun comfortably over the 60min trigger
    disc = sim.discretion_available(state, "FLT-EGW100", "CP1")
    assert disc["overrun_min"] > sim.DISCRETION_REPORT_THRESHOLD_MIN
    sim.assign_crew(state, "FLT-EGW100", "CP1", discretion=True)
    assert state["kpis"]["discretion_reports"] == 1
    crew = state["crew"][0]
    assert crew["discretion_used"]["reportable"] is True
    # Following rest may be reduced, but never below the 10h floor.
    assert crew["rest_floor_next_hr"] == sim.DISCRETION_MIN_REST_AFTER_HR


def test_discretion_is_capped_and_refuses_a_bigger_overrun():
    state, out, back = _timed_out_state()
    back["delay_min"] = 600         # way past any commander's discretion
    disc = sim.discretion_available(state, "FLT-EGW100", "CP1")
    assert disc["available"] is False
    assert disc["overrun_min"] > sim.DISCRETION_MAX_MIN
    res = sim.assign_crew(state, "FLT-EGW100", "CP1", discretion=True)
    assert res["ok"] is False and res["applied"] is False


def test_discretion_cannot_launder_a_non_fdp_breach():
    # Discretion extends duty. It does not make an unrated crew rated, and it
    # must never become a general-purpose override.
    flights = [_flight("EGW900", "G-EAGN", "B777", "10:00", 700, "P9",
                       origin="LHR", destination="JFK")]
    flights[0]["required_crew"]["type_qual"] = "B777"
    crew = [_crew("CP1", "CP", "Larsen", status="available")]
    crew[0]["qualifications"] = ["A320"]        # not rated on the B777
    state = _state(flights, crew=crew)
    disc = sim.discretion_available(state, "FLT-EGW900", "CP1")
    assert disc["available"] is False
    assert "TYPE_QUAL" in disc["reason"]


def test_discretion_declines_when_there_is_nothing_to_extend():
    out = _flight("EGW100", "G-EAGA", "A320", "06:00", 75, "P1", crew_ids=["CP1"])
    state = _state([out], crew=[_crew("CP1", "CP", "Larsen", status="available")])
    disc = sim.discretion_available(state, "FLT-EGW100", "CP1")
    assert disc["available"] is False
    assert "No FDP overrun" in disc["reason"]
