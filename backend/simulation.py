"""
Airline Crew-Control Simulation Engine
=======================================
Domain model + EASA/UK CAA-inspired (simplified) rule checks.
NOTE: This is a SIMULATION for entertainment / training value only.
It is NOT an official compliance tool.
"""

from __future__ import annotations
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# ------------------- Reference data ------------------- #

AIRLINE = {
    "icao": "EGW",
    "name": "Eaglewing International",
    "hub": "LHR",
    "country": "UK",
}

AIRCRAFT_TYPES = {
    "A320": {"seats": 180, "haul": "short", "max_block_hr": 6},
    "A350": {"seats": 325, "haul": "long", "max_block_hr": 14},
    "B777": {"seats": 350, "haul": "long", "max_block_hr": 15},
}

# Fleet: tail registrations
FLEET = [
    {"reg": "G-EAGA", "type": "A320"},
    {"reg": "G-EAGB", "type": "A320"},
    {"reg": "G-EAGC", "type": "A320"},
    {"reg": "G-EAGD", "type": "A320"},
    {"reg": "G-EAGL", "type": "A350"},
    {"reg": "G-EAGM", "type": "A350"},
    {"reg": "G-EAGN", "type": "B777"},
    {"reg": "G-EAGO", "type": "B777"},
]

# Routes: (origin, destination, block_minutes, type_pref)
ROUTES_SHORT = [
    ("LHR", "CDG", 75), ("LHR", "AMS", 75), ("LHR", "FRA", 95),
    ("LHR", "MAD", 145), ("LHR", "BCN", 130), ("LHR", "FCO", 165),
    ("LHR", "DUB", 80), ("LHR", "ZRH", 110), ("LHR", "MXP", 125),
    ("LHR", "CPH", 115),
]
ROUTES_LONG = [
    ("LHR", "JFK", 430, "A350"),
    ("LHR", "DXB", 410, "B777"),
    ("LHR", "SIN", 770, "B777"),
    ("LHR", "HKG", 720, "A350"),
    ("LHR", "LAX", 670, "B777"),
]

CREW_NAMES = [
    "Adeyemi","Bashir","Chen","Davies","Espinoza","Falconer","Gupta","Hadid",
    "Ibrahim","Johansson","Kowalski","Larsen","Mendoza","Nakamura","O'Connor",
    "Park","Quintero","Rasmussen","Sokolov","Tanaka","Ulloa","Vasquez","Wójcik",
    "Xu","Yamada","Zaragoza","Petrov","Olsen","Karim","Singh","Romero","Hassan",
    "Schmidt","Müller","Costa","Reyes","Khan","Brown","Smith","Jones","Wilson",
    "Patel","Ahmed","Garcia","Martinez","Lee","Kim","Wang","Liu","Tanaka",
]

# ------------------- Rules constants ------------------- #
MIN_REST_HOME_HR = 12
MIN_REST_AWAY_HR = 10
MAX_FDP_MIN_2SECTOR = 13 * 60
MAX_FDP_MIN_LONGHAUL = 14 * 60
MAX_BLOCK_28D_HR = 100
MAX_DUTY_7D_HR = 60

# ------------------- Helpers ------------------- #

def _hash_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------- Crew generation ------------------- #

def _generate_crew() -> list[dict]:
    ranks = [
        ("CP", "Captain", 14, "flight_deck"),
        ("FO", "First Officer", 22, "flight_deck"),
        ("SC", "Senior Cabin", 18, "cabin"),
        ("CC", "Cabin Crew", 60, "cabin"),
    ]
    crew = []
    cid = 1000
    used_names: set[str] = set()
    for code, title, count, _crew_group in ranks:
        for _ in range(count):
            # surname + initial unique
            for _try in range(50):
                surname = random.choice(CREW_NAMES)
                initial = random.choice("ABCDEFGHJKLMNPRSTW")
                disp = f"{initial}. {surname}"
                if disp not in used_names:
                    used_names.add(disp)
                    break
            # Qualifications: flight deck almost always single-rated;
            # cabin crew often dual-rated short/long
            if code in ("CP", "FO"):
                quals = [random.choice(["A320", "A350", "B777"])]
                if random.random() < 0.15:
                    second = random.choice([t for t in ["A320", "A350", "B777"] if t != quals[0]])
                    quals.append(second)
            else:
                if random.random() < 0.55:
                    quals = ["A320"]
                else:
                    quals = random.choice([["A350"], ["B777"], ["A320", "A350"], ["A320", "B777"]])
            crew.append({
                "id": f"EGW{cid}",
                "name": disp,
                "rank": code,
                "rank_title": title,
                "base": "LHR",
                "qualifications": quals,
                # Operating state
                "fdp_used_min": 0,
                "block_28d_hr": round(random.uniform(20, 70), 1),
                "duty_7d_hr": round(random.uniform(10, 35), 1),
                "rest_hr_since_duty": round(random.uniform(11, 30), 1),
                "status": "available",        # available | on_duty | rest | standby | sick | off
                "assigned_flight_id": None,
                "fatigue_score": random.randint(15, 45),  # 0-100 lower better
                "sickness_risk": round(random.uniform(0.01, 0.08), 3),
            })
            cid += 1
    return crew


# ------------------- Flight generation ------------------- #

def _add_minutes_to_clock(base_iso: str, minutes: int) -> str:
    base = datetime.fromisoformat(base_iso)
    return (base + timedelta(minutes=minutes)).isoformat()


def _generate_day_flights(day_start_iso: str) -> list[dict]:
    """Generate ~24 flights across the operational day. Mixed short + long haul."""
    flights = []
    # Anchor day at provided iso (will use day-start 04:00 UTC)
    day_start = datetime.fromisoformat(day_start_iso)
    fnum = 100
    # Schedule each aircraft a couple of rotations
    for ac in FLEET:
        depart_min = random.randint(0, 180)  # 0-3h after day start
        rotations = 3 if ac["type"] == "A320" else 1
        for _ in range(rotations):
            if ac["type"] == "A320":
                origin, dest, block = random.choice(ROUTES_SHORT)
                back_origin, back_dest, back_block = dest, origin, block
            else:
                origin, dest, block, type_pref = random.choice(ROUTES_LONG)
                if type_pref != ac["type"]:
                    continue
                back_origin, back_dest, back_block = dest, origin, block

            std = (day_start + timedelta(minutes=depart_min)).isoformat()
            sta = _add_minutes_to_clock(std, block)
            flights.append({
                "id": _hash_id("FLT"),
                "callsign": f"EGW{fnum}",
                "origin": origin,
                "destination": dest,
                "std": std,
                "sta": sta,
                "block_min": block,
                "aircraft_reg": ac["reg"],
                "aircraft_type": ac["type"],
                "status": "scheduled",          # scheduled | boarding | airborne | delayed | cancelled | diverted
                "delay_min": 0,
                "pax_count": random.randint(int(AIRCRAFT_TYPES[ac["type"]]["seats"] * 0.65), AIRCRAFT_TYPES[ac["type"]]["seats"]),
                "assigned_crew_ids": [],
                "required_crew": _required_crew_for(ac["type"], block),
                "note": "",
            })
            fnum += 2
            # Turnaround
            turn = 60 if ac["type"] == "A320" else 180
            depart_min += block + turn
            # Return leg
            std2 = (day_start + timedelta(minutes=depart_min)).isoformat()
            sta2 = _add_minutes_to_clock(std2, back_block)
            flights.append({
                "id": _hash_id("FLT"),
                "callsign": f"EGW{fnum}",
                "origin": back_origin,
                "destination": back_dest,
                "std": std2,
                "sta": sta2,
                "block_min": back_block,
                "aircraft_reg": ac["reg"],
                "aircraft_type": ac["type"],
                "status": "scheduled",
                "delay_min": 0,
                "pax_count": random.randint(int(AIRCRAFT_TYPES[ac["type"]]["seats"] * 0.65), AIRCRAFT_TYPES[ac["type"]]["seats"]),
                "assigned_crew_ids": [],
                "required_crew": _required_crew_for(ac["type"], back_block),
                "note": "",
            })
            fnum += 2
            depart_min += back_block + turn
    flights.sort(key=lambda f: f["std"])
    return flights


def _required_crew_for(ac_type: str, block_min: int) -> dict:
    if ac_type == "A320":
        return {"CP": 1, "FO": 1, "SC": 1, "CC": 3, "type_qual": "A320"}
    # Long-haul: 2 captains if block > 10h
    cps = 2 if block_min > 600 else 1
    return {
        "CP": cps,
        "FO": 2,
        "SC": 1,
        "CC": 7 if ac_type == "B777" else 6,
        "type_qual": ac_type,
    }


# ------------------- Game state factory ------------------- #

def new_game(scenario: str = "default") -> dict:
    """Create a fresh game state."""
    random.seed()
    # Day clock anchored at 04:00 UTC today
    today = datetime.now(timezone.utc).replace(hour=4, minute=0, second=0, microsecond=0)
    day_start_iso = today.isoformat()
    crew = _generate_crew()
    flights = _generate_day_flights(day_start_iso)

    # Mark some crew as standby pool, some on rest
    random.shuffle(crew)
    standby_count = 0
    for c in crew:
        if c["rank"] in ("CP", "FO") and standby_count < 4:
            c["status"] = "standby"
            standby_count += 1
        elif c["rank"] in ("SC", "CC") and standby_count < 14:
            c["status"] = "standby"
            standby_count += 1

    state = {
        "id": _hash_id("GAME"),
        "scenario": scenario,
        "created_at": now_utc_iso(),
        "airline": AIRLINE,
        "fleet": FLEET,
        "crew": crew,
        "flights": flights,
        "incidents": [],
        "decisions_log": [],
        "kpis": {
            "otp_pct": 100.0,
            "legality_breaches": 0,
            "fatigue_index": 25,
            "cost_usd": 0,
            "pax_delay_min": 0,
            "pax_disrupted": 0,
            "score": 1000,
        },
        "day_start": day_start_iso,
        "clock": day_start_iso,                # rolling sim clock
        "phase": "ROSTER",                     # ROSTER | OPS | DEBRIEF
        "tick_count": 0,
        "advisor_history": [],
    }
    return state


# ------------------- Legality / rule checks ------------------- #

def check_assignment(state: dict, flight_id: str, crew_id: str) -> list[dict]:
    """Return list of legality warnings for assigning this crew to this flight.
    Each warning: {code, severity, message, rule_ref}
    """
    warnings: list[dict] = []
    flight = next((f for f in state["flights"] if f["id"] == flight_id), None)
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not flight or not crew:
        warnings.append({
            "code": "REF_NOT_FOUND",
            "severity": "critical",
            "message": "Flight or crew reference not found.",
            "rule_ref": "INTERNAL",
        })
        return warnings

    # Qualification
    type_q = flight["required_crew"]["type_qual"]
    if type_q not in crew["qualifications"]:
        warnings.append({
            "code": "TYPE_QUAL",
            "severity": "critical",
            "message": f"Crew {crew['id']} ({crew['name']}) is not type-rated on {type_q}. Cannot operate this sector.",
            "rule_ref": "EASA FCL.740 (Type Rating Validity)",
        })

    # Already assigned to another flight overlapping in time
    fstd = datetime.fromisoformat(flight["std"])
    fsta = datetime.fromisoformat(flight["sta"])
    for of in state["flights"]:
        if of["id"] == flight_id:
            continue
        if crew_id in of["assigned_crew_ids"]:
            ostd = datetime.fromisoformat(of["std"])
            osta = datetime.fromisoformat(of["sta"])
            if not (fsta <= ostd or osta <= fstd):
                warnings.append({
                    "code": "OVERLAP",
                    "severity": "critical",
                    "message": (
                        f"Crew {crew['id']} already assigned to {of['callsign']} "
                        f"({of['origin']}->{of['destination']}) which overlaps this duty."
                    ),
                    "rule_ref": "ORO.FTL.205 (FDP Limits)",
                })

    # Rest
    if crew["rest_hr_since_duty"] < MIN_REST_HOME_HR:
        warnings.append({
            "code": "MIN_REST",
            "severity": "critical",
            "message": (
                f"Insufficient rest. Crew {crew['id']} has had {crew['rest_hr_since_duty']:.1f}h rest; "
                f"minimum {MIN_REST_HOME_HR}h required at home base before report."
            ),
            "rule_ref": "ORO.FTL.235 (Rest Periods)",
        })

    # Status
    if crew["status"] == "sick":
        warnings.append({
            "code": "STATUS_SICK",
            "severity": "critical",
            "message": f"Crew {crew['id']} is currently flagged SICK and unfit to operate.",
            "rule_ref": "MED.A.020 (Fitness to Fly)",
        })
    elif crew["status"] == "off":
        warnings.append({
            "code": "STATUS_OFF",
            "severity": "warning",
            "message": f"Crew {crew['id']} is on a scheduled day off. Assigning will incur callout cost.",
            "rule_ref": "Industrial Agreement Art. 14",
        })

    # FDP
    block = flight["block_min"]
    projected_fdp = crew["fdp_used_min"] + block + 90  # +90 min for report+post-flight
    fdp_max = MAX_FDP_MIN_LONGHAUL if block > 360 else MAX_FDP_MIN_2SECTOR
    if projected_fdp > fdp_max:
        warnings.append({
            "code": "FDP_EXCEED",
            "severity": "critical",
            "message": (
                f"Flight Duty Period would reach {projected_fdp//60}h{projected_fdp%60:02d}m, "
                f"exceeding the maximum {fdp_max//60}h FDP for this acclimatised report."
            ),
            "rule_ref": "ORO.FTL.205 / CS FTL.1.205",
        })

    # 28-day block hours
    projected_28d = crew["block_28d_hr"] + (block / 60)
    if projected_28d > MAX_BLOCK_28D_HR:
        warnings.append({
            "code": "BLOCK_28D",
            "severity": "critical",
            "message": (
                f"Projected 28-day block hours = {projected_28d:.1f}h, exceeds {MAX_BLOCK_28D_HR}h limit."
            ),
            "rule_ref": "ORO.FTL.210(b)",
        })

    # Fatigue
    if crew["fatigue_score"] > 70:
        warnings.append({
            "code": "FATIGUE_HIGH",
            "severity": "warning",
            "message": (
                f"Crew fatigue score is {crew['fatigue_score']}/100. Consider FRM mitigation or alternative."
            ),
            "rule_ref": "ORO.FTL.120 (Fatigue Management)",
        })

    return warnings


def assign_crew(state: dict, flight_id: str, crew_id: str, force: bool = False) -> dict:
    """Assign a crew member to a flight. Returns {ok, warnings, breaches}."""
    warnings = check_assignment(state, flight_id, crew_id)
    critical = [w for w in warnings if w["severity"] == "critical"]
    if critical and not force:
        return {"ok": False, "warnings": warnings, "applied": False}

    flight = next(f for f in state["flights"] if f["id"] == flight_id)
    crew = next(c for c in state["crew"] if c["id"] == crew_id)
    if crew_id not in flight["assigned_crew_ids"]:
        flight["assigned_crew_ids"].append(crew_id)
    crew["assigned_flight_id"] = flight_id
    if crew["status"] not in ("standby", "off", "sick"):
        crew["status"] = "on_duty"
    # If forced through a critical breach, log it
    if critical and force:
        state["kpis"]["legality_breaches"] += len(critical)
        state["kpis"]["score"] -= 80 * len(critical)
    return {"ok": True, "warnings": warnings, "applied": True}


def unassign_crew(state: dict, flight_id: str, crew_id: str) -> dict:
    flight = next((f for f in state["flights"] if f["id"] == flight_id), None)
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not flight or not crew:
        return {"ok": False}
    if crew_id in flight["assigned_crew_ids"]:
        flight["assigned_crew_ids"].remove(crew_id)
    if crew["assigned_flight_id"] == flight_id:
        crew["assigned_flight_id"] = None
        if crew["status"] == "on_duty":
            crew["status"] = "available"
    return {"ok": True}


def roster_completeness(state: dict) -> dict:
    """How many flights have complete required crew."""
    total = len(state["flights"])
    complete = 0
    missing: list[dict] = []
    for f in state["flights"]:
        req = f["required_crew"]
        need = req["CP"] + req["FO"] + req["SC"] + req["CC"]
        have = len(f["assigned_crew_ids"])
        # Cheap counter by rank
        rank_counts = {"CP": 0, "FO": 0, "SC": 0, "CC": 0}
        for cid in f["assigned_crew_ids"]:
            c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
            if c:
                rank_counts[c["rank"]] = rank_counts.get(c["rank"], 0) + 1
        ok = all(rank_counts[r] >= req[r] for r in ("CP", "FO", "SC", "CC"))
        if ok:
            complete += 1
        else:
            missing.append({
                "flight_id": f["id"],
                "callsign": f["callsign"],
                "need": {r: max(0, req[r] - rank_counts[r]) for r in ("CP","FO","SC","CC")},
                "have": rank_counts,
                "total_have": have,
                "total_need": need,
            })
    return {"total": total, "complete": complete, "missing": missing}


# ------------------- Day-of-Ops simulation ------------------- #

INCIDENT_TYPES = [
    ("CREW_SICK", 0.30, "Crew reported sick before report time."),
    ("LATE_REPORT", 0.15, "Crew running late for report."),
    ("WEATHER", 0.20, "Weather disruption at destination."),
    ("TECH", 0.20, "Technical defect / MEL deferral on aircraft."),
    ("ATC_FLOW", 0.15, "ATC slot / flow restriction imposed."),
]


def tick(state: dict, minutes: int = 30) -> dict:
    """Advance the simulation clock by `minutes`. May spawn incidents."""
    if state["phase"] != "OPS":
        return {"ok": False, "reason": "Not in OPS phase"}
    state["tick_count"] += 1
    clock = datetime.fromisoformat(state["clock"]) + timedelta(minutes=minutes)
    state["clock"] = clock.isoformat()

    new_incidents = []
    # Spawn 0-2 incidents per tick weighted
    n = random.choices([0, 1, 2], weights=[50, 35, 15])[0]
    for _ in range(n):
        kind, _w, desc = random.choices(
            INCIDENT_TYPES,
            weights=[i[1] for i in INCIDENT_TYPES],
            k=1
        )[0]
        # Pick an affected flight that has not yet departed
        upcoming = [f for f in state["flights"] if f["status"] in ("scheduled","delayed","boarding") and datetime.fromisoformat(f["std"]) > clock - timedelta(hours=2)]
        if not upcoming:
            continue
        flight = random.choice(upcoming)
        sev = random.choice(["minor", "major"])
        inc = {
            "id": _hash_id("INC"),
            "type": kind,
            "severity": sev,
            "description": desc,
            "raised_at": state["clock"],
            "flight_id": flight["id"],
            "flight_callsign": flight["callsign"],
            "status": "open",
            "resolution": None,
            "options": _recovery_options_for(kind),
        }
        # Apply immediate impact
        if kind == "CREW_SICK" and flight["assigned_crew_ids"]:
            # mark one assigned crew as sick
            cid = random.choice(flight["assigned_crew_ids"])
            c = next(cc for cc in state["crew"] if cc["id"] == cid)
            c["status"] = "sick"
            c["assigned_flight_id"] = None
            flight["assigned_crew_ids"].remove(cid)
            inc["affected_crew_id"] = cid
            inc["affected_crew_name"] = c["name"]
        elif kind == "WEATHER":
            flight["delay_min"] += 45 if sev == "minor" else 120
            flight["status"] = "delayed"
        elif kind == "TECH":
            flight["delay_min"] += 60 if sev == "minor" else 240
            flight["status"] = "delayed"
        elif kind == "ATC_FLOW":
            flight["delay_min"] += 30 if sev == "minor" else 90
            flight["status"] = "delayed"
        elif kind == "LATE_REPORT":
            flight["delay_min"] += 20 if sev == "minor" else 60
            flight["status"] = "delayed"

        new_incidents.append(inc)
        state["incidents"].append(inc)

    _recompute_kpis(state)
    return {"ok": True, "new_incidents": new_incidents, "clock": state["clock"]}


def _recovery_options_for(kind: str) -> list[dict]:
    base = [
        {"action": "delay", "label": "Hold / Accept Delay", "cost_usd": 5000, "otp_hit": 8, "fatigue": 2},
        {"action": "cancel", "label": "Cancel Flight", "cost_usd": 80000, "otp_hit": 0, "pax_disrupt": True},
    ]
    if kind == "CREW_SICK":
        return [
            {"action": "callout_standby", "label": "Call Out Standby Crew", "cost_usd": 3000, "otp_hit": 2, "fatigue": 5},
            {"action": "swap_crew", "label": "Swap From Adjacent Pairing", "cost_usd": 1500, "otp_hit": 4, "fatigue": 3},
            {"action": "deadhead", "label": "Position Crew (Deadhead)", "cost_usd": 4500, "otp_hit": 12, "fatigue": 8},
            *base,
        ]
    if kind == "TECH":
        return [
            {"action": "aircraft_swap", "label": "Swap Aircraft From Spare", "cost_usd": 12000, "otp_hit": 18, "fatigue": 1},
            {"action": "mel_defer", "label": "Accept MEL Deferral", "cost_usd": 800, "otp_hit": 4, "fatigue": 0},
            *base,
        ]
    if kind == "WEATHER":
        return [
            {"action": "reroute", "label": "Reroute / Alternate Airport", "cost_usd": 20000, "otp_hit": 25, "fatigue": 4, "pax_disrupt": True},
            *base,
        ]
    if kind == "ATC_FLOW":
        return [
            {"action": "request_slot", "label": "Request Earlier CTOT Slot", "cost_usd": 600, "otp_hit": 6, "fatigue": 0},
            *base,
        ]
    if kind == "LATE_REPORT":
        return [
            {"action": "warn_crew", "label": "Issue Verbal Warning", "cost_usd": 0, "otp_hit": 2, "fatigue": 1},
            *base,
        ]
    return base


def resolve_incident(state: dict, incident_id: str, action: str) -> dict:
    inc = next((i for i in state["incidents"] if i["id"] == incident_id), None)
    if not inc:
        return {"ok": False, "reason": "incident not found"}
    if inc["status"] != "open":
        return {"ok": False, "reason": "already resolved"}
    chosen = next((o for o in inc["options"] if o["action"] == action), None)
    if not chosen:
        return {"ok": False, "reason": "invalid action"}
    # Apply
    flight = next((f for f in state["flights"] if f["id"] == inc["flight_id"]), None)
    cost = chosen.get("cost_usd", 0)
    otp_hit = chosen.get("otp_hit", 0)
    fatigue = chosen.get("fatigue", 0)
    pax_disrupt = chosen.get("pax_disrupt", False)

    state["kpis"]["cost_usd"] += cost
    state["kpis"]["fatigue_index"] = min(100, state["kpis"]["fatigue_index"] + fatigue)
    if flight:
        if action == "cancel":
            flight["status"] = "cancelled"
            state["kpis"]["pax_disrupted"] += flight.get("pax_count", 0)
            state["kpis"]["pax_delay_min"] += 240 * flight.get("pax_count", 0)
        elif action == "callout_standby":
            # find a standby crew that fits the missing role
            req = flight["required_crew"]
            type_q = req["type_qual"]
            current_ranks = {"CP":0,"FO":0,"SC":0,"CC":0}
            for cid in flight["assigned_crew_ids"]:
                c = next((cc for cc in state["crew"] if cc["id"]==cid), None)
                if c:
                    current_ranks[c["rank"]] += 1
            missing_rank = None
            for r in ("CP","FO","SC","CC"):
                if current_ranks[r] < req[r]:
                    missing_rank = r
                    break
            if missing_rank:
                candidate = next((c for c in state["crew"] if c["status"]=="standby" and c["rank"]==missing_rank and type_q in c["qualifications"]), None)
                if candidate:
                    candidate["status"] = "on_duty"
                    candidate["assigned_flight_id"] = flight["id"]
                    flight["assigned_crew_ids"].append(candidate["id"])
                    inc["replacement_crew_id"] = candidate["id"]
                    inc["replacement_crew_name"] = candidate["name"]
                else:
                    inc["resolution_note"] = "No standby crew of correct rank/qualification available — delay incurred."
                    flight["delay_min"] += 60
        elif action == "swap_crew":
            flight["delay_min"] += 20
        elif action == "aircraft_swap":
            # swap to a similar type spare reg if any
            spare = next((a for a in FLEET if a["type"] == flight["aircraft_type"] and a["reg"] != flight["aircraft_reg"]), None)
            if spare:
                flight["aircraft_reg"] = spare["reg"]
            flight["delay_min"] += 45
        elif action == "reroute":
            flight["status"] = "diverted"
            flight["delay_min"] += 180
            state["kpis"]["pax_disrupted"] += int(flight.get("pax_count", 0) * 0.5)
        elif action == "delay":
            flight["delay_min"] += 30
            flight["status"] = "delayed"
        elif action == "mel_defer":
            flight["note"] = "MEL deferral accepted"
        elif action == "request_slot":
            flight["delay_min"] = max(0, flight["delay_min"] - 15)
        elif action == "warn_crew":
            pass
        elif action == "deadhead":
            flight["delay_min"] += 45

        if pax_disrupt and action != "cancel":
            state["kpis"]["pax_disrupted"] += int(flight.get("pax_count", 0) * 0.4)
        state["kpis"]["pax_delay_min"] += flight.get("delay_min", 0)

    inc["status"] = "resolved"
    inc["resolution"] = action
    inc["resolution_label"] = chosen["label"]
    inc["resolved_at"] = state["clock"]
    state["decisions_log"].append({
        "ts": state["clock"], "incident_id": incident_id, "action": action,
        "cost_usd": cost, "otp_hit": otp_hit
    })
    _recompute_kpis(state)
    return {"ok": True, "incident": inc, "kpis": state["kpis"]}


def _recompute_kpis(state: dict) -> None:
    flights = state["flights"]
    if not flights:
        return
    on_time = sum(1 for f in flights if f.get("delay_min", 0) <= 15 and f["status"] != "cancelled")
    state["kpis"]["otp_pct"] = round(100.0 * on_time / len(flights), 1)
    # Score
    s = 1000
    s -= state["kpis"]["legality_breaches"] * 80
    s -= int(state["kpis"]["cost_usd"] / 1000)
    s -= int(state["kpis"]["pax_disrupted"] / 5)
    s -= max(0, int((75 - state["kpis"]["otp_pct"]) * 5))
    state["kpis"]["score"] = s


def start_day(state: dict) -> dict:
    if state["phase"] != "ROSTER":
        return {"ok": False, "reason": "already started"}
    state["phase"] = "OPS"
    return {"ok": True}


def end_day(state: dict) -> dict:
    state["phase"] = "DEBRIEF"
    _recompute_kpis(state)
    open_inc = [i for i in state["incidents"] if i["status"] == "open"]
    return {
        "ok": True,
        "kpis": state["kpis"],
        "flights": state["flights"],
        "open_incidents": len(open_inc),
        "decisions": state["decisions_log"],
    }


def summarize_state_for_advisor(state: dict, focus_incident_id: str | None = None) -> dict:
    """Compact state summary for the LLM advisor."""
    upcoming = []
    clock = datetime.fromisoformat(state["clock"])
    for f in state["flights"]:
        std = datetime.fromisoformat(f["std"])
        if std >= clock - timedelta(hours=1) and std <= clock + timedelta(hours=4):
            upcoming.append({
                "callsign": f["callsign"],
                "ac_type": f["aircraft_type"],
                "route": f"{f['origin']}-{f['destination']}",
                "std": f["std"][11:16],
                "status": f["status"],
                "delay_min": f["delay_min"],
                "crew_assigned": len(f["assigned_crew_ids"]),
                "crew_required_total": sum(f["required_crew"][r] for r in ("CP","FO","SC","CC")),
            })
    standby = {
        "CP": sum(1 for c in state["crew"] if c["status"]=="standby" and c["rank"]=="CP"),
        "FO": sum(1 for c in state["crew"] if c["status"]=="standby" and c["rank"]=="FO"),
        "SC": sum(1 for c in state["crew"] if c["status"]=="standby" and c["rank"]=="SC"),
        "CC": sum(1 for c in state["crew"] if c["status"]=="standby" and c["rank"]=="CC"),
    }
    sick = sum(1 for c in state["crew"] if c["status"]=="sick")
    open_inc = [i for i in state["incidents"] if i["status"]=="open"]
    focus = None
    if focus_incident_id:
        focus = next((i for i in state["incidents"] if i["id"]==focus_incident_id), None)
    return {
        "airline": state["airline"]["name"],
        "phase": state["phase"],
        "clock_utc": state["clock"][11:16],
        "kpis": state["kpis"],
        "standby_pool": standby,
        "sick_count": sick,
        "open_incidents": [{
            "id": i["id"], "type": i["type"], "severity": i["severity"],
            "flight": i["flight_callsign"], "desc": i["description"],
        } for i in open_inc[:6]],
        "upcoming_flights": upcoming[:8],
        "focus_incident": focus,
    }


# ------------------- MongoDB-safe sanitiser ------------------- #

def strip_mongo_id(doc: dict) -> dict:
    if not doc:
        return doc
    doc = dict(doc)
    doc.pop("_id", None)
    return doc
