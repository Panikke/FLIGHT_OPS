"""Backend tests for multi-day campaign: /api/sim/{id}/next_day endpoint
and related state mutations (carry-over fatigue, 28-day block, night-stop returns)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    _env = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
    if not os.path.exists(_env):
        _env = "/app/frontend/.env"
    with open(_env) as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def fresh_game(session):
    r = session.post(f"{API}/sim/new", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _find_lh_flight_safe(state):
    """Pick the long-haul flight with the smallest block_min (LHR-JFK ~430 is safest re FDP)."""
    lh = [f for f in state["flights"] if f["aircraft_type"] in ("A350", "B777")
          and f["origin"] == "LHR"]
    assert lh, "No long-haul outbound flights generated"
    lh.sort(key=lambda f: f["block_min"])
    return lh[0]


def _pick_crew_for(state, flight, rank):
    type_q = flight["required_crew"]["type_qual"]
    return next(c for c in state["crew"]
                if c["rank"] == rank
                and type_q in c["qualifications"]
                and c["status"] in ("available", "standby")
                and c["rest_hr_since_duty"] >= 12)


# ---- A. next_day requires DEBRIEF phase ----
def test_next_day_requires_debrief(session, fresh_game):
    gid = fresh_game["id"]
    r = session.post(f"{API}/sim/{gid}/next_day", timeout=15)
    assert r.status_code == 400, f"Expected 400 while in ROSTER, got {r.status_code}: {r.text}"


# ---- B. Full day-1 -> day-2 cycle with long-haul night-stop assignment ----
@pytest.fixture(scope="module")
def cycled(session, fresh_game):
    """Run a complete day-1 cycle, assign crew to a safe long-haul flight,
    end_day, then capture the next_day response."""
    gid = fresh_game["id"]
    # Re-fetch (assign-flow test in other file may have mutated this state)
    state = session.get(f"{API}/sim/{gid}", timeout=15).json()
    if state["phase"] != "ROSTER":
        # If a previous test left it elsewhere, just start a brand new game
        state = session.post(f"{API}/sim/new", timeout=30).json()
        gid = state["id"]

    # Pick a safe long-haul flight (smallest block_min)
    lh = _find_lh_flight_safe(state)
    cp = _pick_crew_for(state, lh, "CP")

    # Snapshot day-1 fatigue baseline for the assigned crew + a NON-flying crew
    cp_id = cp["id"]
    fatigue_day1_cp = cp["fatigue_score"]
    # Choose a control crew (different rank, will NOT be assigned anywhere we control)
    control = next(c for c in state["crew"] if c["rank"] == "CC"
                   and c["id"] != cp_id and c["status"] == "available")
    control_id = control["id"]
    fatigue_day1_control = control["fatigue_score"]

    # Assign CP to long-haul flight (force=True to bypass any soft FO/SC gaps)
    ra = session.post(f"{API}/sim/{gid}/assign/{lh['id']}",
                      json={"crew_id": cp_id, "force": True}, timeout=15)
    assert ra.status_code == 200 and ra.json()["applied"]

    # Start day -> tick a couple of times -> end day
    rs = session.post(f"{API}/sim/{gid}/start_day", timeout=15)
    assert rs.status_code == 200
    for _ in range(3):
        session.post(f"{API}/sim/{gid}/tick", json={"minutes": 30}, timeout=20)
    re = session.post(f"{API}/sim/{gid}/end_day", timeout=15)
    assert re.status_code == 200

    # Capture day-1 final state
    day1_state = session.get(f"{API}/sim/{gid}", timeout=15).json()
    assert day1_state["phase"] == "DEBRIEF"

    # Advance to day 2
    rn = session.post(f"{API}/sim/{gid}/next_day", timeout=20)
    assert rn.status_code == 200, rn.text
    next_resp = rn.json()

    day2_state = session.get(f"{API}/sim/{gid}", timeout=15).json()

    return {
        "game_id": gid,
        "lh_flight_day1": lh,
        "cp_id": cp_id,
        "control_id": control_id,
        "fatigue_day1_cp": fatigue_day1_cp,
        "fatigue_day1_control": fatigue_day1_control,
        "day1_state": day1_state,
        "next_resp": next_resp,
        "day2_state": day2_state,
    }


def test_next_day_response_shape(cycled):
    j = cycled["next_resp"]
    assert j["day_number"] == 2
    assert "pre_rostered_returns" in j
    assert j["pre_rostered_returns"] >= 1, "Should pre-roster at least 1 LH return"
    assert "campaign_kpis" in j
    assert "state" in j
    assert j["state"]["phase"] == "ROSTER"


def test_state_advanced_to_day2(cycled):
    s = cycled["day2_state"]
    assert s["day_number"] == 2
    assert s["phase"] == "ROSTER"
    assert s["incidents"] == []
    assert s["decisions_log"] == []
    assert s["tick_count"] == 0
    # day_start advanced by ~24h
    from datetime import datetime
    d1 = datetime.fromisoformat(cycled["day1_state"]["day_start"])
    d2 = datetime.fromisoformat(s["day_start"])
    delta_hr = (d2 - d1).total_seconds() / 3600
    assert 23.5 <= delta_hr <= 24.5


def test_long_haul_return_pre_rostered(cycled):
    """The LH outbound from day 1 should have a corresponding return on day 2
    with the SAME crew_id in assigned_crew_ids and note containing RETURN FROM NIGHT-STOP."""
    out = cycled["lh_flight_day1"]
    cp_id = cycled["cp_id"]
    s2 = cycled["day2_state"]
    # Find a flight in day 2 that is the reverse route (dest -> origin)
    returns = [f for f in s2["flights"]
               if f["origin"] == out["destination"] and f["destination"] == out["origin"]]
    assert returns, f"No return flight {out['destination']}->{out['origin']} on day 2"
    # At least one of these returns carries cp_id and has the RETURN note
    matched = [f for f in returns
               if cp_id in f["assigned_crew_ids"]
               and "RETURN FROM NIGHT-STOP" in (f.get("note") or "")]
    assert matched, (f"Expected a {out['destination']}->{out['origin']} return on day 2 "
                     f"carrying crew {cp_id} with RETURN note. Returns found: "
                     f"{[(f['callsign'], f['assigned_crew_ids'], f.get('note')) for f in returns]}")


def test_campaign_kpis_after_one_day(cycled):
    ck = cycled["day2_state"]["campaign_kpis"]
    assert ck["days_completed"] == 1
    assert isinstance(ck["total_score"], int)
    assert len(ck["per_day"]) == 1
    assert ck["per_day"][0]["day"] == 1
    assert "score" in ck["per_day"][0]
    assert "otp" in ck["per_day"][0]
    assert "breaches" in ck["per_day"][0]


def test_block_history_and_28d_window(cycled):
    cp_id = cycled["cp_id"]
    cp = next(c for c in cycled["day2_state"]["crew"] if c["id"] == cp_id)
    assert "block_history" in cp
    assert len(cp["block_history"]) == 1
    # block_28d_hr should equal sum of block_history (within rounding)
    assert abs(cp["block_28d_hr"] - sum(cp["block_history"])) < 0.2
    # The assigned crew should have flown >0 hours
    assert cp["block_history"][0] > 0


def test_fatigue_carryover(cycled):
    cp_id = cycled["cp_id"]
    control_id = cycled["control_id"]
    cp_d2 = next(c for c in cycled["day2_state"]["crew"] if c["id"] == cp_id)
    ctl_d2 = next(c for c in cycled["day2_state"]["crew"] if c["id"] == control_id)
    # CP operated -> fatigue went UP
    assert cp_d2["fatigue_score"] > cycled["fatigue_day1_cp"], (
        f"Fatigue should have increased for operating crew: "
        f"{cycled['fatigue_day1_cp']} -> {cp_d2['fatigue_score']}"
    )
    # Control didn't operate -> fatigue went DOWN (or stayed at floor 5)
    assert ctl_d2["fatigue_score"] < cycled["fatigue_day1_control"] or ctl_d2["fatigue_score"] == 5


def test_second_day_cycle(session, cycled):
    """Run another day cycle and verify campaign_kpis grows correctly."""
    gid = cycled["game_id"]
    session.post(f"{API}/sim/{gid}/start_day", timeout=15)
    for _ in range(2):
        session.post(f"{API}/sim/{gid}/tick", json={"minutes": 30}, timeout=20)
    session.post(f"{API}/sim/{gid}/end_day", timeout=15)
    rn = session.post(f"{API}/sim/{gid}/next_day", timeout=20)
    assert rn.status_code == 200
    j = rn.json()
    assert j["day_number"] == 3
    ck = j["campaign_kpis"]
    assert ck["days_completed"] == 2
    assert len(ck["per_day"]) == 2
    assert ck["per_day"][0]["day"] == 1
    assert ck["per_day"][1]["day"] == 2
