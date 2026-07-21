"""Backend tests for OCC Sim API (FastAPI + Mongo + emergentintegrations)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback - read frontend .env (repo-relative; /app for container deploys)
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
def game(session):
    r = session.post(f"{API}/sim/new", timeout=30)
    assert r.status_code == 200, r.text
    state = r.json()
    return state


# ---- 1. health ----
def test_root(session):
    r = session.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert j.get("service") == "OCC Sim"


# ---- 2. new sim shape ----
def test_new_game_shape(game):
    assert game["phase"] == "ROSTER"
    assert len(game["crew"]) >= 100
    assert 15 <= len(game["flights"]) <= 40
    assert len(game["fleet"]) == 8
    assert "kpis" in game and "otp_pct" in game["kpis"]
    assert "_id" not in game


# ---- 3. get state ----
def test_get_state(session, game):
    r = session.get(f"{API}/sim/{game['id']}", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["id"] == game["id"]
    assert "_id" not in j


# ---- 4. roster status ----
def test_roster_status(session, game):
    r = session.get(f"{API}/sim/{game['id']}/roster_status", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert "total" in j and "complete" in j and "missing" in j
    assert j["total"] == len(game["flights"])


def _pick_flight_and_crews(session, state):
    """Return (flight, valid_crew_id, invalid_qual_crew_id) for assignment tests.
    `valid` is verified live via /check_assignment rather than just matching
    rank+qualification — crew rest hours are randomised per game (11-30h vs a
    12h minimum), so a rank+qual match alone isn't guaranteed to be legal."""
    game_id = state["id"]
    flight = state["flights"][0]
    type_q = flight["required_crew"]["type_qual"]
    candidates = [c for c in state["crew"] if c["rank"] == "CP" and type_q in c["qualifications"]
                  and c["status"] in ("available", "standby")]
    valid = None
    for c in candidates:
        r = session.post(f"{API}/sim/{game_id}/check_assignment/{flight['id']}",
                          json={"crew_id": c["id"]}, timeout=15)
        if r.status_code == 200 and not r.json().get("has_critical"):
            valid = c
            break
    assert valid is not None, "no legal CP candidate found for the assign-flow tests"
    invalid = next(c for c in state["crew"] if c["rank"] == "CP" and type_q not in c["qualifications"])
    return flight, valid["id"], invalid["id"]


# ---- 5. check_assignment ----
def test_check_assignment(session, game):
    flight, valid_id, invalid_id = _pick_flight_and_crews(session, game)
    r = session.post(f"{API}/sim/{game['id']}/check_assignment/{flight['id']}",
                     json={"crew_id": invalid_id}, timeout=15)
    assert r.status_code == 200
    j = r.json()
    codes = [w["code"] for w in j["warnings"]]
    assert "TYPE_QUAL" in codes
    assert j["has_critical"] is True


# ---- 6. assign valid + invalid + force ----
def test_assign_flow(session, game):
    flight, valid_id, invalid_id = _pick_flight_and_crews(session, game)
    # valid
    r = session.post(f"{API}/sim/{game['id']}/assign/{flight['id']}",
                     json={"crew_id": valid_id}, timeout=15)
    assert r.status_code == 200
    jr = r.json()
    assert jr["ok"] is True and jr["applied"] is True

    # invalid (no force) -> applied false
    r2 = session.post(f"{API}/sim/{game['id']}/assign/{flight['id']}",
                      json={"crew_id": invalid_id}, timeout=15)
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["applied"] is False
    assert any(w["code"] == "TYPE_QUAL" for w in j2["warnings"])

    # invalid + force -> applied true and legality_breaches up
    before = session.get(f"{API}/sim/{game['id']}", timeout=15).json()["kpis"]["legality_breaches"]
    r3 = session.post(f"{API}/sim/{game['id']}/assign/{flight['id']}",
                      json={"crew_id": invalid_id, "force": True}, timeout=15)
    assert r3.status_code == 200
    assert r3.json()["applied"] is True
    after = session.get(f"{API}/sim/{game['id']}", timeout=15).json()["kpis"]["legality_breaches"]
    assert after > before


# ---- 7. unassign ----
def test_unassign(session, game):
    flight = game["flights"][0]
    state = session.get(f"{API}/sim/{game['id']}", timeout=15).json()
    cur_flight = next(f for f in state["flights"] if f["id"] == flight["id"])
    assert len(cur_flight["assigned_crew_ids"]) >= 1
    crew_id = cur_flight["assigned_crew_ids"][0]
    r = session.post(f"{API}/sim/{game['id']}/unassign/{flight['id']}/{crew_id}", timeout=15)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    state2 = session.get(f"{API}/sim/{game['id']}", timeout=15).json()
    f2 = next(f for f in state2["flights"] if f["id"] == flight["id"])
    assert crew_id not in f2["assigned_crew_ids"]


# ---- 8. start_day, tick, resolve, end_day ----
def test_ops_phase_flow(session, game):
    r = session.post(f"{API}/sim/{game['id']}/start_day", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["state"]["phase"] == "OPS"

    # tick a few times until at least one incident appears
    incident = None
    last_clock = None
    for _ in range(15):
        rt = session.post(f"{API}/sim/{game['id']}/tick", json={"minutes": 30}, timeout=20)
        assert rt.status_code == 200
        jt = rt.json()
        assert jt["ok"] is True
        last_clock = jt["clock"]
        opens = [i for i in jt["incidents"] if i["status"] == "open"]
        if opens:
            incident = opens[0]
            break
    assert last_clock is not None
    # tick must have advanced clock - compare with day_start
    assert last_clock != game["clock"]

    if incident:
        # options carry live feasibility — pick the first feasible one
        action = next(o["action"] for o in incident["options"] if o.get("feasible", True))
        rr = session.post(f"{API}/sim/{game['id']}/resolve/{incident['id']}",
                          json={"action": action}, timeout=15)
        assert rr.status_code == 200
        jr = rr.json()
        assert jr["ok"] is True
        assert jr["incident"]["status"] == "resolved"

    # end day
    re = session.post(f"{API}/sim/{game['id']}/end_day", timeout=15)
    assert re.status_code == 200
    je = re.json()
    assert je["ok"] is True
    assert "kpis" in je
    st = session.get(f"{API}/sim/{game['id']}", timeout=15).json()
    assert st["phase"] == "DEBRIEF"


# ---- 9. advisor (LLM) ----
def test_advisor(session, game):
    r = session.post(f"{API}/sim/{game['id']}/advisor",
                     json={"question": "Give a short status of operations."},
                     timeout=90)
    assert r.status_code == 200
    j = r.json()
    assert "response" in j and isinstance(j["response"], str) and len(j["response"]) > 0


# ---- 10. 404 for unknown game ----
def test_unknown_game(session):
    r = session.get(f"{API}/sim/GAME-NOPE", timeout=15)
    assert r.status_code == 404
