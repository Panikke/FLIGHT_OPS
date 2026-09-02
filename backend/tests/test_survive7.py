"""Iteration 5: Survive 7 + Bunk-based FDP extension tests."""
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulation as sim  # noqa: E402


def _load_frontend_url():
    # Env var wins; otherwise read frontend/.env repo-relative first so the
    # suite runs on a dev machine, falling back to /app for container deploys.
    # (Same order as test_occ_backend.py / test_pairings.py / test_campaign.py.)
    url = os.environ.get("REACT_APP_BACKEND_URL", "")
    if url:
        return url
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env"),
        "/app/frontend/.env",
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p) as fh:
                for ln in fh:
                    if ln.startswith("REACT_APP_BACKEND_URL="):
                        return ln.split("=", 1)[1].strip().strip('"')
    return ""


BASE_URL = _load_frontend_url().rstrip('/')
API = f"{BASE_URL}/api"


# free_play deliberately reseeds from OS entropy — a player's game must not be
# reproducible — so whether the generated day contains a ULR (>540min block)
# sector is luck. The bunk/augmentation tests below build their state in process
# under this seed instead of rolling the dice over HTTP: it yields three ULR
# sectors across both wide-body types (LHR-LAX and LHR-SIN on the B777, LHR-HKG
# on the A350). No seed is plumbed through POST /api/sim/new on purpose — that
# would let a player reroll a game.
ULR_SEED = 4


def _new(scenario=None):
    body = {"scenario": scenario} if scenario else {}
    r = requests.post(f"{API}/sim/new", json=body, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---- Bunk + augmented crew ----
class TestBunkFDP:
    def test_long_haul_ulr_requires_augmented_crew(self):
        s = sim.new_game("free_play", seed=ULR_SEED)
        lh = [f for f in s["flights"] if f["block_min"] > 540]
        assert lh, f"seed {ULR_SEED} no longer generates a ULR sector"
        for f in lh:
            # A single Captain operates every sector; augmentation is carried
            # entirely by relief First Officers (see simulation._relief_pilots_for).
            assert f["required_crew"]["CP"] == 1, f
            assert f["required_crew"]["FO"] >= 2, f
            assert f["aircraft_type"] in ("A350", "B777")

    def test_short_haul_unaugmented(self):
        s = _new("free_play")
        sh = [f for f in s["flights"] if f["aircraft_type"] == "A320"]
        assert sh
        for f in sh:
            assert f["required_crew"]["CP"] == 1
            assert f["required_crew"]["FO"] == 1

    def test_precheck_message_mentions_18h_bunk_extension(self):
        s = sim.new_game("free_play", seed=ULR_SEED)
        ulr = next(f for f in s["flights"] if f["block_min"] > 540)
        cap, basis = sim._fdp_cap_for_flight(ulr)
        assert cap == 18 * 60
        assert "Class 1 bunks" in basis
        assert ulr["aircraft_type"] in basis

        # The cap only ever reaches the controller through the FDP_EXCEED
        # message, and only when the projection actually busts it — so bust it.
        # A Captain already 12h into an FDP cannot then take a 12h+ ULR sector
        # on top of it, and the message has to say which cap it broke. Standby
        # crew are skipped: home standby beyond the free hours cuts the cap
        # below 18h (CS FTL.1.225), which is a different message.
        cp = next(c for c in s["crew"]
                  if c["rank"] == "CP"
                  and ulr["aircraft_type"] in c["qualifications"]
                  and c["status"] != "standby")
        cp["fdp_used_min"] = 12 * 60
        warnings = sim.check_assignment(s, ulr["id"], cp["id"])
        msg = next(w["message"] for w in warnings if w["code"] == "FDP_EXCEED")
        assert "18h FDP applicable" in msg
        assert "Class 1 bunks" in msg
        assert ulr["aircraft_type"] in msg


# ---- Survive 7 scenario ----
class TestSurvive7:
    def test_new_game_challenge_metadata(self):
        s = _new("survive_7")
        assert s["is_challenge"] is True
        assert s["total_days"] == 7
        assert s["day_number"] == 1
        assert s["campaign_complete"] is False
        assert s["final_grade"] is None

    def test_fixed_seed_reproducible(self):
        s1 = _new("survive_7")
        s2 = _new("survive_7")
        # crew first id and first flight callsign deterministic
        assert s1["crew"][0]["id"] == s2["crew"][0]["id"]
        assert s1["flights"][0]["callsign"] == s2["flights"][0]["callsign"]

    def test_free_play_metadata(self):
        s = _new("free_play")
        assert s["is_challenge"] is False
        assert s["total_days"] is None

    def test_no_body_defaults_free_play(self):
        r = requests.post(f"{API}/sim/new", timeout=30)
        assert r.status_code == 200
        s = r.json()
        assert s["is_challenge"] is False


# ---- Difficulty curve ----
class TestDifficultyCurve:
    def _count_incidents_on_day(self, day):
        import sys
        sys.path.insert(0, "/app/backend")
        import simulation as simmod
        # Build a survive_7 state in-memory and tick repeatedly. survive_7
        # already reseeds internally to a fixed value for leaderboard
        # reproducibility, so no explicit seed is needed (a prior
        # random.seed(1234) here was dead code — new_game() overwrote it).
        state = simmod.new_game("survive_7")
        state["day_number"] = day
        state["phase"] = "OPS"
        total = 0
        for _ in range(20):
            # A major TECH grounding freezes the whole clock until the player
            # decides (see is_clock_paused), and this probe never decides. Left
            # alone it wedges on the first grounding — which on day 7, where
            # tech_mult is 2.5, happens almost immediately and would make the
            # busiest day look like the quietest. Stand in for a controller who
            # keeps up, so what this measures is the spawn RATE.
            for inc in state["incidents"]:
                if inc.get("requires_aircraft_decision") and inc["status"] == "open":
                    inc["requires_aircraft_decision"] = False
                    inc["status"] = "resolved"
            res = simmod.tick(state, minutes=30)
            total += len(res.get("new_incidents", []))
        return total

    def test_day7_more_incidents_than_day1(self):
        d1 = self._count_incidents_on_day(1)
        d7 = self._count_incidents_on_day(7)
        print(f"day1={d1} day7={d7}")
        assert d7 > d1


# ---- Campaign finalization ----
class TestCampaignFinalize:
    def test_seven_day_full_loop_via_api(self):
        s = _new("survive_7")
        gid = s["id"]
        for day in range(1, 7 + 1):
            # start_day → end_day immediately (no assignments needed)
            r = requests.post(f"{API}/sim/{gid}/start_day", timeout=30)
            assert r.status_code == 200
            r = requests.post(f"{API}/sim/{gid}/end_day", timeout=30)
            assert r.status_code == 200
            r = requests.post(f"{API}/sim/{gid}/next_day", timeout=30)
            assert r.status_code == 200
            j = r.json()
            if day == 7:
                assert j["campaign_complete"] is True
                fg = j["final_grade"]
                assert fg["label"] in ("DISTINGUISHED", "PASS", "WEAK PASS", "MARGINAL", "FAILED")
                assert "total_score" in fg and "total_breaches" in fg
                assert "avg_otp_pct" in fg and "days_completed" in fg
                # State remains in DEBRIEF, no day 8
                state2 = requests.get(f"{API}/sim/{gid}", timeout=30).json()
                assert state2["phase"] == "DEBRIEF"
                assert state2["campaign_complete"] is True
                assert state2["day_number"] == 7
            else:
                assert j.get("campaign_complete") is not True
