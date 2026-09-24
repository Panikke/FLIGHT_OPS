"""Focused unit coverage for the LIVE OCC common operating picture."""
from datetime import datetime, timedelta

import simulation as sim


def _ops_state(seed=17):
    state = sim.new_game("free_play", seed=seed)
    state["phase"] = "OPS"
    return state


def test_aog_holds_only_its_rotation_while_clock_keeps_running(monkeypatch):
    state = _ops_state()
    flight = min(state["flights"], key=lambda f: f["std"])
    start = datetime.fromisoformat(state["day_start"])
    flight["std"] = (start + timedelta(minutes=30)).isoformat()
    flight["sta"] = (start + timedelta(minutes=120)).isoformat()
    state["flights"] = [flight]
    state["clock"] = state["day_start"]
    monkeypatch.setattr(sim, "BASE_INCIDENT_RATE_PER_HOUR", 0)
    monkeypatch.setattr(sim.random, "randint", lambda _low, _high: 120)

    sim._ground_aircraft(state, flight["aircraft_reg"], "Hydraulic indication", state["clock"])
    incident = {
        "id": "INC-AOG", "type": "TECH", "severity": "major",
        "description": "Hydraulic indication", "raised_at": state["clock"],
        "flight_id": flight["id"], "flight_callsign": flight["callsign"],
        "status": "open", "resolution": None, "options": [], "escalated": False,
        "requires_aircraft_decision": True, "grounded_reg": flight["aircraft_reg"],
    }
    state["incidents"].append(incident)

    first = sim.tick(state, minutes=60)
    assert first["clock"].endswith("05:00:00+00:00")
    assert "paused" not in first
    assert first["aog_holds"] == [{
        "flight_id": flight["id"], "callsign": flight["callsign"],
        "reg": flight["aircraft_reg"], "hold_min": 30,
    }]
    assert flight["status"] == "delayed"
    assert flight["delay_min"] == 30
    assert incident["status"] == "open"

    second = sim.tick(state, minutes=60)
    assert flight["aircraft_reg"] in second["aircraft_released"]
    assert second["maintenance_rectified"] == [incident["id"]]
    assert incident["status"] == "resolved"
    assert flight["status"] == "airborne"


def test_operational_workspace_prioritises_aog_and_exposes_tail_impact():
    state = _ops_state()
    flights = sorted(state["flights"], key=lambda f: f["std"])
    aog_flight, minor_flight = flights[0], flights[1]
    aog_flight["delay_min"] = 40
    state["incidents"] = [
        {
            "id": "INC-MINOR", "type": "WEATHER", "severity": "minor",
            "description": "Convective weather", "raised_at": state["clock"],
            "flight_id": minor_flight["id"], "flight_callsign": minor_flight["callsign"],
            "status": "open", "escalated": False,
        },
        {
            "id": "INC-AOG", "type": "TECH", "severity": "major",
            "description": "Hydraulic indication", "raised_at": state["clock"],
            "flight_id": aog_flight["id"], "flight_callsign": aog_flight["callsign"],
            "status": "open", "escalated": False, "requires_aircraft_decision": True,
            "grounded_reg": aog_flight["aircraft_reg"],
        },
    ]

    workspace = sim.operational_workspace(state, minor_flight["id"])

    assert workspace["priority_queue"][0]["incident_id"] == "INC-AOG"
    expected_downstream = [f for f in state["flights"]
                           if f["aircraft_reg"] == aog_flight["aircraft_reg"]
                           and f["std"] > aog_flight["std"]
                           and f["status"] in sim._AC_ACTIVE_STATUSES]
    assert workspace["priority_queue"][0]["downstream_sectors"] == len(expected_downstream)
    assert workspace["priority_queue"][0]["active_delay_min"] == 40
    assert workspace["selected"]["flight"]["id"] == minor_flight["id"]
    assert workspace["selected"]["aircraft"]["reg"] == minor_flight["aircraft_reg"]
    assert any(
        flight["id"] == minor_flight["id"]
        for tail in workspace["network"]
        for flight in tail["flights"]
    )
