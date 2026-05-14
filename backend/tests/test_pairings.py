"""Tests for out-and-back pairing realism (iter 3 feature)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
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
    return r.json()


# ---- A) short-haul flights come in pairs sharing pairing_id ----
def test_shorthaul_pairings(game):
    shorthaul = [f for f in game["flights"] if f["aircraft_type"] == "A320"]
    assert len(shorthaul) > 0
    # Each pairing_id for A320 should have exactly 2 sectors
    pid_to_flights: dict = {}
    for f in shorthaul:
        pid_to_flights.setdefault(f["pairing_id"], []).append(f)
    assert len(pid_to_flights) > 0
    for pid, fls in pid_to_flights.items():
        assert len(fls) == 2, f"A320 pairing {pid} has {len(fls)} sectors, expected 2"
        # Outbound and return: same airports flipped
        o, r = sorted(fls, key=lambda x: x["std"])
        assert o["origin"] == r["destination"]
        assert o["destination"] == r["origin"]


# ---- B) long-haul flights are solo with their own pairing_id ----
def test_longhaul_solo_pairings(game):
    longhaul = [f for f in game["flights"] if f["aircraft_type"] in ("A350", "B777")]
    assert len(longhaul) > 0
    pid_counts: dict = {}
    for f in longhaul:
        pid_counts[f["pairing_id"]] = pid_counts.get(f["pairing_id"], 0) + 1
    for pid, cnt in pid_counts.items():
        assert cnt == 1, f"Long-haul pairing {pid} has {cnt} sectors, expected 1"


# ---- C) assign on outbound -> both sectors share crew, response.pairing_sectors==2 ----
def test_assign_propagates_to_pairing(session, game):
    # find a fresh A320 pairing with no crew
    pid_to_flights: dict = {}
    for f in game["flights"]:
        if f["aircraft_type"] == "A320":
            pid_to_flights.setdefault(f["pairing_id"], []).append(f)
    pair = None
    for pid, fls in pid_to_flights.items():
        if all(len(x["assigned_crew_ids"]) == 0 for x in fls):
            pair = sorted(fls, key=lambda x: x["std"])
            break
    assert pair, "no clean A320 pairing found"
    outbound, ret = pair
    # find a CP crew with A320 qual and clean status
    crew = next(
        c for c in game["crew"]
        if c["rank"] == "CP" and "A320" in c["qualifications"]
        and c["status"] in ("available", "standby")
        and c["rest_hr_since_duty"] >= 12
    )
    r = session.post(
        f"{API}/sim/{game['id']}/assign/{outbound['id']}",
        json={"crew_id": crew["id"]}, timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is True
    assert body.get("pairing_sectors") == 2, f"expected 2 sectors got {body}"

    # GET state: both sectors should have crew_id
    state = session.get(f"{API}/sim/{game['id']}", timeout=15).json()
    f_out = next(f for f in state["flights"] if f["id"] == outbound["id"])
    f_ret = next(f for f in state["flights"] if f["id"] == ret["id"])
    assert crew["id"] in f_out["assigned_crew_ids"]
    assert crew["id"] in f_ret["assigned_crew_ids"]

    # D) unassign on RETURN should remove from BOTH sectors
    ru = session.post(
        f"{API}/sim/{game['id']}/unassign/{ret['id']}/{crew['id']}", timeout=15
    )
    assert ru.status_code == 200
    body_u = ru.json()
    assert body_u["ok"] is True
    assert body_u.get("pairing_sectors") == 2
    state2 = session.get(f"{API}/sim/{game['id']}", timeout=15).json()
    f_out2 = next(f for f in state2["flights"] if f["id"] == outbound["id"])
    f_ret2 = next(f for f in state2["flights"] if f["id"] == ret["id"])
    assert crew["id"] not in f_out2["assigned_crew_ids"]
    assert crew["id"] not in f_ret2["assigned_crew_ids"]
