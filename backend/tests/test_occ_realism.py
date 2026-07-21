"""Unit tests for the OCC-realism mechanics: incident desk/IATA-code metadata,
escalation of unattended incidents, and EU261-style passenger compensation.

Pure engine tests (no running server needed), following test_curfew.py's pattern.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulation as sim  # noqa: E402


@pytest.fixture(autouse=True)
def _no_random_spawns(monkeypatch):
    """Zero the spawn rate so a randomly-spawned incident can't add delay to
    the flight under test and flake the exact-value assertions. The spawn path
    itself is covered by the integration suite."""
    monkeypatch.setattr(sim, "BASE_INCIDENT_RATE_PER_HOUR", 0)


def _flight(callsign, std, block_min=75, pax=150, delay=0, status="scheduled"):
    std_iso = f"2026-06-12T{std}:00+00:00"
    sta = sim._add_minutes_to_clock(std_iso, block_min)
    return {
        "id": f"FLT-{callsign}",
        "callsign": callsign,
        "origin": "LHR",
        "destination": "CDG",
        "std": std_iso,
        "sta": sta,
        "block_min": block_min,
        "aircraft_reg": "G-EAGA",
        "aircraft_type": "A320",
        "status": status,
        "delay_min": delay,
        "pax_count": pax,
        "assigned_crew_ids": [],
        "required_crew": {"CP": 1, "FO": 1, "SC": 1, "CC": 4, "type_qual": "A320"},
        "pairing_id": f"PAIR-{callsign}",
        "note": "",
    }


def _state(flights, clock_iso, incidents=None):
    return {
        "flights": flights,
        "crew": [],
        "incidents": incidents or [],
        "tick_count": 0,
        "phase": "OPS",
        "clock": clock_iso,
        "is_challenge": False,
        "kpis": {
            "otp_pct": 100.0, "legality_breaches": 0, "curfew_violations": 0,
            "compensation_usd": 0, "fatigue_index": 25, "cost_usd": 0,
            "pax_delay_min": 0, "pax_disrupted": 0, "score": 1000,
        },
    }


def _incident(flight, raised_iso, kind="TECH", status="open"):
    meta = sim.INCIDENT_META[kind]
    return {
        "id": "INC-TEST01",
        "type": kind,
        "severity": "minor",
        "description": "test incident",
        "raised_at": raised_iso,
        "flight_id": flight["id"],
        "flight_callsign": flight["callsign"],
        "status": status,
        "resolution": None,
        "options": [],
        "reported_by": meta["desk"],
        "delay_code": meta["delay_code"],
        "escalated": False,
    }


# ---- Metadata ----

def test_every_incident_type_has_desk_and_delay_code():
    for kind, _w, _d in sim.INCIDENT_TYPES:
        meta = sim.INCIDENT_META[kind]
        assert meta["desk"], kind
        assert meta["delay_code"].isdigit() and len(meta["delay_code"]) == 2, kind


# ---- Escalation ----

def test_unattended_incident_escalates():
    f = _flight("EGW100", "12:00")
    inc = _incident(f, "2026-06-12T09:00:00+00:00")  # raised long ago
    state = _state([f], "2026-06-12T10:00:00+00:00", incidents=[inc])
    res = sim.tick(state, minutes=30)
    assert inc["escalated"] is True
    assert inc["severity"] == "major"
    assert f["delay_min"] == sim.ESCALATION_EXTRA_DELAY_MIN
    assert f["status"] == "delayed"
    assert inc["options"], "menu should be re-priced from live state"
    assert "MAJOR" in inc["escalation_note"]
    assert any(e["incident_id"] == inc["id"] for e in res["escalations"])


def test_fresh_incident_does_not_escalate():
    f = _flight("EGW100", "12:00")
    inc = _incident(f, "2026-06-12T09:55:00+00:00")  # 35 min old after the tick
    state = _state([f], "2026-06-12T10:00:00+00:00", incidents=[inc])
    sim.tick(state, minutes=30)
    assert inc["escalated"] is False
    assert inc["severity"] == "minor"


def test_escalation_happens_only_once():
    f = _flight("EGW100", "12:00")
    inc = _incident(f, "2026-06-12T08:00:00+00:00")
    state = _state([f], "2026-06-12T10:00:00+00:00", incidents=[inc])
    sim.tick(state, minutes=30)
    delay_after_first = f["delay_min"]
    res2 = sim.tick(state, minutes=30)
    assert f["delay_min"] == delay_after_first  # no repeat bump from escalation
    assert not any(e["incident_id"] == inc["id"] for e in res2["escalations"])


def test_resolved_or_departed_incident_never_escalates():
    f_air = _flight("EGW200", "06:00", status="airborne")
    inc_air = _incident(f_air, "2026-06-12T05:00:00+00:00")
    f_res = _flight("EGW300", "12:00")
    inc_res = _incident(f_res, "2026-06-12T05:00:00+00:00", status="resolved")
    state = _state([f_air, f_res], "2026-06-12T08:00:00+00:00",
                   incidents=[inc_air, inc_res])
    res = sim.tick(state, minutes=15)
    assert res["escalations"] == []
    assert inc_air["escalated"] is False
    assert inc_res["escalated"] is False


def test_escalation_makes_mel_deferral_infeasible():
    # MEL deferral is minor-only; after escalation to major it must be closed.
    f = _flight("EGW100", "12:00")
    inc = _incident(f, "2026-06-12T08:00:00+00:00", kind="TECH")
    state = _state([f], "2026-06-12T10:00:00+00:00", incidents=[inc])
    sim.tick(state, minutes=30)
    mel = next(o for o in inc["options"] if o["action"] == "mel_defer")
    assert mel["feasible"] is False


# ---- EU261-style compensation ----

def test_compensation_charged_at_landing_over_threshold():
    f = _flight("EGW100", "06:00", block_min=75, pax=100, delay=200, status="delayed")
    state = _state([f], "2026-06-12T10:00:00+00:00")
    res = sim.tick(state, minutes=60)   # clock 11:00 > sta(07:15)+200min(10:35)
    assert f["status"] == "landed"
    assert f["comp_charged"] is True
    expected = 100 * sim.COMP_SHORT_HAUL_USD
    assert state["kpis"]["compensation_usd"] == expected
    assert state["kpis"]["cost_usd"] >= expected
    assert "EU261 COMP DUE" in f["note"]
    assert any(c["callsign"] == "EGW100" and c["amount_usd"] == expected
               for c in res["compensation_events"])


def test_no_compensation_under_threshold():
    f = _flight("EGW100", "06:00", delay=120, status="delayed")
    state = _state([f], "2026-06-12T10:00:00+00:00")
    sim.tick(state, minutes=60)
    assert f["status"] == "landed"
    assert not f.get("comp_charged")
    assert state["kpis"]["compensation_usd"] == 0


def test_weather_exemption_blocks_compensation():
    # Extraordinary circumstances (weather/ATC) exempt the airline under EU261.
    f = _flight("EGW100", "06:00", delay=300, status="delayed")
    f["comp_exempt"] = True
    state = _state([f], "2026-06-12T11:00:00+00:00")
    sim.tick(state, minutes=90)
    assert f["status"] == "landed"
    assert not f.get("comp_charged")
    assert state["kpis"]["compensation_usd"] == 0


def test_long_haul_rate_and_single_charge():
    f = _flight("EGW146", "05:00", block_min=430, pax=200, delay=240, status="delayed")
    state = _state([f], "2026-06-12T15:00:00+00:00")
    sim.tick(state, minutes=90)
    assert f["status"] == "landed"
    expected = 200 * sim.COMP_LONG_HAUL_USD
    assert state["kpis"]["compensation_usd"] == expected
    sim.tick(state, minutes=30)   # further ticks must not double-charge
    assert state["kpis"]["compensation_usd"] == expected


def test_weather_incident_marks_flight_exempt():
    assert "WEATHER" in sim.COMP_EXEMPT_INCIDENT_TYPES
    assert "ATC_FLOW" in sim.COMP_EXEMPT_INCIDENT_TYPES
    assert "TECH" not in sim.COMP_EXEMPT_INCIDENT_TYPES  # airline-controllable


def test_restart_day_rearms_comp_and_curfew_flags():
    f = _flight("EGW100", "06:00", delay=200, status="delayed")
    f["comp_charged"] = True
    f["comp_exempt"] = True
    f["curfew_dep_checked"] = True
    f["curfew_arr_checked"] = True
    f["curfew_violation"] = "departure"
    state = _state([f], "2026-06-12T12:00:00+00:00")
    state["day_start"] = "2026-06-12T04:00:00+00:00"
    state["decisions_log"] = []
    sim.restart_day(state)
    for key in ("comp_charged", "comp_exempt", "curfew_dep_checked",
                "curfew_arr_checked", "curfew_violation"):
        assert key not in f, key
