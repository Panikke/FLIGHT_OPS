"""The crew disposition desk: the page where a stranded crew gets dealt with.

Before this existed, `crew_irregularities` raised a CREW_OUT_OF_POSITION
warning whose own message ended "position them or replace them" — and neither
verb was reachable from anywhere in the UI or the API.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulation as sim  # noqa: E402
from test_tier3 import _crew, _flight, _state  # noqa: E402


@pytest.fixture(autouse=True)
def _no_random_spawns(monkeypatch):
    monkeypatch.setattr(sim, "BASE_INCIDENT_RATE_PER_HOUR", 0)


def _stranded_state(**kw):
    """A CP sitting at MAD with a sector home available later today."""
    homebound = _flight("EGW250", "G-EAGB", "A320", "16:00", 145, "P2",
                        origin="MAD", destination="LHR")
    crew = [_crew("CP1", "CP", "Larsen", station="MAD")]
    return _state([homebound], crew=crew, **kw), crew[0], homebound


# ------------------------------------------------------------ the population

def test_a_normal_night_stop_is_not_a_disposition_case():
    # A crew down-route with their return already rostered out of the station
    # they are standing in is ordinary long-haul, not a problem. 49 of these
    # would bury the handful that actually need a call.
    back = _flight("EGW901", "G-EAGN", "B777", "06:00", 770, "P8",
                   origin="SIN", destination="LHR", crew_ids=["CP1"])
    crew = [_crew("CP1", "CP", "Larsen", station="SIN")]
    state = _state([back], crew=crew, fleet=[{"reg": "G-EAGN", "type": "B777"}])
    assert sim.crew_disposition(state) == []


def test_a_crew_who_cannot_reach_their_duty_is_the_urgent_case():
    duty = _flight("EGW300", "G-EAGA", "A320", "16:00", 75, "P3",
                   origin="LHR", destination="CDG", crew_ids=["CP1"])
    crew = [_crew("CP1", "CP", "Larsen", station="JFK")]
    state = _state([duty], crew=crew)
    rows = sim.crew_disposition(state)
    assert len(rows) == 1
    assert rows[0]["why"] == "unreachable_duty"
    assert rows[0]["at"] == "JFK"
    assert rows[0]["next_duty"]["reachable"] is False


def test_a_crew_adrift_with_nothing_rostered_shows_up():
    crew = [_crew("CP1", "CP", "Larsen", station="AMS")]
    state = _state([], crew=crew)
    rows = sim.crew_disposition(state)
    assert len(rows) == 1 and rows[0]["why"] == "no_way_back"


def test_crew_at_base_are_never_listed():
    state = _state([], crew=[_crew("CP1", "CP", "Larsen")])
    assert sim.crew_disposition(state) == []


# ---------------------------------------------------------------- the levers

def test_position_home_finds_a_real_sector_and_prices_it():
    state, crew, homebound = _stranded_state()
    rows = sim.crew_disposition(state)
    opt = next(o for o in rows[0]["options"] if o["action"] == "position_home")
    assert opt["feasible"] is True
    assert "EGW250" in opt["label"]
    assert opt["cost_usd"] == sim.DEADHEAD_SEAT_USD + sim.DEADHEAD_HANDLING_USD


def test_position_home_is_refused_when_nothing_connects():
    crew = [_crew("CP1", "CP", "Larsen", station="AMS")]
    state = _state([], crew=crew)
    opt = next(o for o in sim.crew_disposition(state)[0]["options"]
               if o["action"] == "position_home")
    assert opt["feasible"] is False
    assert "AMS to LHR" in opt["reason"]


def test_positioning_home_moves_them_and_charges_the_duty():
    state, crew, homebound = _stranded_state()
    res = sim.dispose_crew(state, "CP1", "position_home")
    assert res["applied"] is True
    # ORO.FTL.215: positioning is duty and FDP, but it is not a sector.
    assert crew["fdp_used_min"] == homebound["block_min"]
    assert crew["station"] == "LHR"
    assert crew["positioning"][0]["to"] == "LHR"
    assert state["kpis"]["cost_usd"] == res["cost_usd"]


def test_night_stop_is_always_possible_and_always_billed():
    # It is what happens by default if the player does nothing; making it
    # explicit and billed is the point.
    crew = [_crew("CP1", "CP", "Larsen", station="AMS")]
    state = _state([], crew=crew)
    opt = next(o for o in sim.crew_disposition(state)[0]["options"]
               if o["action"] == "night_stop")
    assert opt["feasible"] is True
    assert opt["cost_usd"] == (
        sim.CREW_HOTEL_USD + sim.CREW_TRANSPORT_USD + sim.CREW_PERDIEM_USD)

    res = sim.dispose_crew(state, "CP1", "night_stop")
    assert res["applied"] is True
    assert crew[0]["status"] == "rest"
    assert crew[0]["hotac_nights"] == 1
    assert state["kpis"]["hotac_usd"] == opt["cost_usd"]


def test_holding_downroute_needs_something_to_hold_for():
    crew = [_crew("CP1", "CP", "Larsen", station="AMS")]
    state = _state([], crew=crew)
    opt = next(o for o in sim.crew_disposition(state)[0]["options"]
               if o["action"] == "hold_downroute")
    assert opt["feasible"] is False
    assert "Nothing rostered" in opt["reason"]


def test_recrew_locally_is_shown_as_impossible_rather_than_hidden():
    # For a single-base airline this is usually infeasible. Saying so plainly
    # is more useful than omitting the option.
    duty = _flight("EGW300", "G-EAGA", "A320", "16:00", 75, "P3",
                   origin="CDG", destination="LHR", crew_ids=["CP1"])
    crew = [_crew("CP1", "CP", "Larsen", station="JFK")]
    state = _state([duty], crew=crew)
    opt = next(o for o in sim.crew_disposition(state)[0]["options"]
               if o["action"] == "recrew_local")
    assert opt["feasible"] is False
    assert "No legal crew already at" in opt["reason"]


# ------------------------------------------------------------- housekeeping

def test_preview_prices_without_committing():
    state, crew, _ = _stranded_state()
    pv = sim.preview_crew_disposition(state, "CP1", "position_home")
    assert pv["ok"] is True
    assert pv["option"]["cost_usd"] > 0
    # Read-only.
    assert state["kpis"]["cost_usd"] == 0
    assert crew.get("positioning") is None


def test_an_unknown_action_is_refused():
    state, _, _ = _stranded_state()
    assert sim.dispose_crew(state, "CP1", "teleport")["applied"] is False


def test_every_disposition_is_logged_for_the_debrief():
    state, _, _ = _stranded_state()
    sim.dispose_crew(state, "CP1", "position_home")
    entry = state["decisions_log"][-1]
    assert entry["action"] == "disposition_position_home"
    assert entry["incident_type"] == "CREW_DISPOSITION"
    assert entry["cost_usd"] > 0


def test_ending_the_day_away_from_base_is_billed_even_if_ignored():
    # The whole reason "hold them down-route" never felt like a decision is
    # that doing nothing was silent and free.
    import random
    random.seed(3)
    st = sim.new_game("free_play")
    sim.auto_roster(st)
    sim.start_day(st)
    for _ in range(24):
        sim.tick(st, minutes=60)
    sim.end_day(st)
    res = sim.advance_to_next_day(st)
    assert res["hotac_usd"] > 0
    assert st["kpis"]["hotac_usd"] == res["hotac_usd"]
    assert any(c.get("hotac_nights") for c in st["crew"])


# ------------------------------------------------------- roster planner

def test_a_duty_cell_carries_the_shape_of_the_duty():
    # "FLT" told the player nothing: an 05:00 four-sector day and a 14:00
    # single-sector day rendered identically, though every fatigue rule in the
    # engine distinguishes them.
    import random
    random.seed(2)
    st = sim.new_game("free_play")
    sim.auto_roster(st)
    sim.start_day(st)
    roster = sim.crew_roster(st)
    cell = next(
        c for row in roster["crew"] for c in row["cells"] if c.get("route")
    )
    assert cell["code"] == "FLT"
    assert cell["route"].count("-") >= 1
    assert len(cell["report_z"]) == 5 and len(cell["off_duty_z"]) == 5
    assert cell["sectors"] >= 1
    assert 0 < cell["fdp_min"] <= cell["fdp_cap_min"]
    assert cell["over_cap"] is False


def test_open_time_lists_uncovered_flying_with_who_could_take_it():
    import random
    random.seed(2)
    st = sim.new_game("free_play")        # nothing rostered yet
    rows = sim.open_time(st)
    assert rows, "a fresh game has every sector open"
    assert sum(r["short_by"] for r in rows) > 0
    first = rows[0]
    assert first["needs"]
    # Every open rank offers legal candidates, drawn from the same legality
    # engine the assign modal uses.
    for rank in first["needs"]:
        assert rank in first["candidates"]
    assert rows == sorted(rows, key=lambda r: r["std"])


def test_open_time_empties_once_the_roster_is_filled():
    import random
    random.seed(2)
    st = sim.new_game("free_play")
    sim.auto_roster(st)
    assert sim.open_time(st) == []


def test_open_time_ignores_cancelled_flying():
    f = _flight("EGW100", "G-EAGA", "A320", "10:00", 75, "P1", crew_ids=[])
    f["status"] = "cancelled"
    state = _state([f], crew=[_crew("CP1", "CP", "Larsen")])
    assert sim.open_time(state) == []
