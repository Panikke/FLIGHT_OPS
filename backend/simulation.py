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
    # crew_rest_class: "none" | "class_3" (seat) | "class_2" (recliner) | "class_1" (bunk)
    # Class 1 bunks + augmented crew allow extended FDP (per CS-FTL.1.205(d))
    "A320": {"seats": 180, "haul": "short", "max_block_hr": 6, "crew_rest_class": "none"},
    "A350": {"seats": 325, "haul": "long", "max_block_hr": 14, "crew_rest_class": "class_1"},
    "B777": {"seats": 350, "haul": "long", "max_block_hr": 15, "crew_rest_class": "class_1"},
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
MAX_FDP_MIN_2SECTOR = 13 * 60         # short-haul, unaugmented
MAX_FDP_MIN_LONGHAUL_BASE = 14 * 60   # long-haul unaugmented
MAX_FDP_MIN_LONGHAUL_BUNK = 18 * 60   # long-haul, augmented crew + Class 1 bunks
MAX_BLOCK_28D_HR = 100
MAX_DUTY_7D_HR = 60


def _fdp_cap_for_flight(flight: dict) -> tuple[int, str]:
    """Return (max_fdp_min, basis_str) for a flight given aircraft + crew complement."""
    ac_type = flight["aircraft_type"]
    block = flight["block_min"]
    if block <= 360:
        return MAX_FDP_MIN_2SECTOR, "short-haul, 2-sector acclimatised"
    # Long-haul
    rest_class = AIRCRAFT_TYPES.get(ac_type, {}).get("crew_rest_class", "none")
    req = flight.get("required_crew", {})
    augmented = req.get("CP", 1) >= 2 and req.get("FO", 1) >= 2
    if augmented and rest_class == "class_1":
        return MAX_FDP_MIN_LONGHAUL_BUNK, f"long-haul augmented crew + Class 1 bunks ({ac_type})"
    return MAX_FDP_MIN_LONGHAUL_BASE, f"long-haul ({ac_type}) without bunk/augment extension"

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
    """Generate flights for the operational day.
    Short-haul: aircraft does multiple out-and-back rotations from LHR.
      Each (outbound + return) pair shares a `pairing_id` — the same crew set
      operates both sectors (realistic short-haul operation).
    Long-haul: aircraft does ONE outbound today; the return is a next-day
      operation (crew night-stops downroute). Pairing_id is unique to that
      single sector for the day.
    """
    flights = []
    day_start = datetime.fromisoformat(day_start_iso)
    fnum = 100
    for ac in FLEET:
        depart_min = random.randint(0, 180)
        if ac["type"] == "A320":
            # 2 to 3 out-and-back rotations in the day, each = 1 pairing
            rotations = random.choice([2, 3])
            for _ in range(rotations):
                origin, dest, block = random.choice(ROUTES_SHORT)
                pairing_id = _hash_id("PAIR")
                std = (day_start + timedelta(minutes=depart_min)).isoformat()
                sta = _add_minutes_to_clock(std, block)
                out = _make_flight(fnum, origin, dest, std, sta, block, ac, pairing_id)
                flights.append(out)
                fnum += 2
                turn = 60
                depart_min += block + turn
                std2 = (day_start + timedelta(minutes=depart_min)).isoformat()
                sta2 = _add_minutes_to_clock(std2, block)
                back = _make_flight(fnum, dest, origin, std2, sta2, block, ac, pairing_id)
                flights.append(back)
                fnum += 2
                depart_min += block + turn
        else:
            # Long-haul: ONE sector today (outbound), crew night-stops.
            # No same-day return — that's tomorrow's problem.
            choices = [r for r in ROUTES_LONG if r[3] == ac["type"]]
            if not choices:
                continue
            origin, dest, block, _type_pref = random.choice(choices)
            std = (day_start + timedelta(minutes=depart_min)).isoformat()
            sta = _add_minutes_to_clock(std, block)
            pairing_id = _hash_id("PAIR")
            flights.append(_make_flight(fnum, origin, dest, std, sta, block, ac, pairing_id))
            fnum += 2
    flights.sort(key=lambda f: f["std"])
    return flights


def _make_flight(fnum, origin, dest, std, sta, block, ac, pairing_id):
    return {
        "id": _hash_id("FLT"),
        "callsign": f"EGW{fnum}",
        "origin": origin,
        "destination": dest,
        "std": std,
        "sta": sta,
        "block_min": block,
        "aircraft_reg": ac["reg"],
        "aircraft_type": ac["type"],
        "status": "scheduled",
        "delay_min": 0,
        "pax_count": random.randint(
            int(AIRCRAFT_TYPES[ac["type"]]["seats"] * 0.65),
            AIRCRAFT_TYPES[ac["type"]]["seats"],
        ),
        "assigned_crew_ids": [],
        "required_crew": _required_crew_for(ac["type"], block),
        "pairing_id": pairing_id,
        "note": "",
    }


def _required_crew_for(ac_type: str, block_min: int) -> dict:
    if ac_type == "A320":
        return {"CP": 1, "FO": 1, "SC": 1, "CC": 3, "type_qual": "A320"}
    # Long-haul: augmented crew (2 CP + 2 FO) on sectors that need extended FDP.
    # Threshold ~9h block ≈ projected FDP > 11h → augmentation needed.
    augmented = block_min > 540  # >9h
    return {
        "CP": 2 if augmented else 1,
        "FO": 2 if augmented else 2,  # long-haul always 2 FOs
        "SC": 1,
        "CC": 7 if ac_type == "B777" else 6,
        "type_qual": ac_type,
    }


# ------------------- Game state factory ------------------- #

def new_game(scenario: str = "free_play") -> dict:
    """Create a fresh game state.
    scenario: 'free_play' (open-ended) or 'survive_7' (7-day fixed-seed challenge)
    """
    is_challenge = scenario == "survive_7"
    if is_challenge:
        # Fixed seed makes the challenge reproducible (and leaderboard-able)
        random.seed(20260514)
    else:
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
        # ---- Multi-day campaign tracking ----
        "day_number": 1,
        "campaign_kpis": {
            "days_completed": 0,
            "total_score": 0,
            "total_breaches": 0,
            "total_cost_usd": 0,
            "total_pax_disrupted": 0,
            "avg_otp_pct": 0.0,
            "per_day": [],   # list of {day, score, otp, breaches, cost}
        },
        # Crew downroute (waiting for tomorrow's return)
        "outstation_crew": [],   # list of {crew_id, station, flight_id_to_return}
        # Scenario / challenge mode
        "is_challenge": is_challenge,
        "total_days": 7 if is_challenge else None,
        "campaign_complete": False,
        "final_grade": None,
    }
    return state


# ------------------- Multi-day campaign ------------------- #

def _final_grade(ck: dict) -> dict:
    """Compute final challenge grade based on campaign KPIs."""
    score = ck.get("total_score", 0)
    breaches = ck.get("total_breaches", 0)
    avg_otp = ck.get("avg_otp_pct", 0)
    days = ck.get("days_completed", 0)
    if breaches >= 10 or score <= 0:
        label, tone, note = "FAILED", "t-crit", "Authority audit triggered. Operating certificate at risk."
    elif breaches >= 5 or avg_otp < 60:
        label, tone, note = "MARGINAL", "t-warn", "You survived, but the regulator wrote you up."
    elif score >= 5500 and breaches == 0 and avg_otp >= 85:
        label, tone, note = "DISTINGUISHED", "t-nominal", "Textbook campaign. Promoted to Head of Crew Control."
    elif score >= 4000 and avg_otp >= 75:
        label, tone, note = "PASS", "t-nominal", "A clean, professional week. The CEO sends congratulations."
    else:
        label, tone, note = "WEAK PASS", "t-warn", "You got through it. Just."
    return {
        "label": label, "tone": tone, "note": note,
        "total_score": score, "total_breaches": breaches,
        "avg_otp_pct": avg_otp, "days_completed": days,
    }


def advance_to_next_day(state: dict) -> dict:
    """Roll the simulation to the next operational day.
    If is_challenge and current day == total_days: finalize the campaign instead
    (no further day generated; set campaign_complete and final_grade).
    """
    # Capture today
    day_kpis = dict(state["kpis"])
    ck = state.setdefault("campaign_kpis", {
        "days_completed": 0, "total_score": 0, "total_breaches": 0,
        "total_cost_usd": 0, "total_pax_disrupted": 0, "avg_otp_pct": 0.0, "per_day": []
    })
    ck["days_completed"] += 1
    ck["total_score"] += day_kpis["score"]
    ck["total_breaches"] += day_kpis["legality_breaches"]
    ck["total_cost_usd"] += day_kpis["cost_usd"]
    ck["total_pax_disrupted"] += day_kpis["pax_disrupted"]
    ck["per_day"].append({
        "day": state.get("day_number", 1),
        "score": day_kpis["score"],
        "otp": day_kpis["otp_pct"],
        "breaches": day_kpis["legality_breaches"],
        "cost": day_kpis["cost_usd"],
    })
    if ck["per_day"]:
        ck["avg_otp_pct"] = round(
            sum(d["otp"] for d in ck["per_day"]) / len(ck["per_day"]), 1
        )

    # Challenge mode: campaign complete after total_days
    if state.get("is_challenge") and state.get("day_number", 1) >= state.get("total_days", 7):
        state["campaign_complete"] = True
        state["final_grade"] = _final_grade(ck)
        # Keep phase at DEBRIEF (player can review and start new campaign)
        return {
            "day_number": state["day_number"],
            "pre_rostered_returns": 0,
            "campaign_kpis": ck,
            "campaign_complete": True,
            "final_grade": state["final_grade"],
        }

    # Per-crew block flown today
    today_block_by_crew: dict[str, float] = {}
    long_haul_assignments: dict[str, dict] = {}  # crew_id -> {station, route_back, ...}
    for f in state["flights"]:
        if f["status"] == "cancelled":
            continue
        block_hr = f["block_min"] / 60.0
        for cid in f["assigned_crew_ids"]:
            today_block_by_crew[cid] = today_block_by_crew.get(cid, 0) + block_hr
        # Long-haul outbound — crew is now downroute and must operate the return tomorrow
        if f["aircraft_type"] in ("A350", "B777") and f["status"] != "cancelled":
            for cid in f["assigned_crew_ids"]:
                long_haul_assignments[cid] = {
                    "station": f["destination"],
                    "origin": f["destination"],
                    "destination": f["origin"],
                    "block_min": f["block_min"],
                    "aircraft_reg": f["aircraft_reg"],
                    "aircraft_type": f["aircraft_type"],
                }

    # Update crew
    for c in state["crew"]:
        flown = today_block_by_crew.get(c["id"], 0)
        c.setdefault("block_history", [])
        c["block_history"].append(flown)
        # keep sliding window of last 28 days
        if len(c["block_history"]) > 28:
            c["block_history"] = c["block_history"][-28:]
        c["block_28d_hr"] = round(sum(c["block_history"]), 1)
        c["fdp_used_min"] = 0
        # Fatigue update
        if flown > 0:
            c["fatigue_score"] = min(100, c["fatigue_score"] + random.randint(8, 18))
        else:
            c["fatigue_score"] = max(5, c["fatigue_score"] - random.randint(6, 12))
        # Rest
        c["rest_hr_since_duty"] = round(random.uniform(11, 30), 1) if flown == 0 else round(random.uniform(12, 18), 1)
        # Recover most sick crew
        if c["status"] == "sick":
            if random.random() < 0.7:
                c["status"] = "available"
        else:
            # Clear assignment for tomorrow (will be re-rostered)
            c["assigned_flight_id"] = None
            c["status"] = "available"
        # Sickness risk drift
        if c["fatigue_score"] > 70 and random.random() < 0.05:
            c["status"] = "sick"

    # Re-establish standby pool (~10% of pool from those still available)
    available = [c for c in state["crew"] if c["status"] == "available"]
    random.shuffle(available)
    standby_count = 0
    for c in available:
        if c["rank"] in ("CP", "FO") and standby_count < 4:
            c["status"] = "standby"
            standby_count += 1
        elif c["rank"] in ("SC", "CC") and standby_count < 14:
            c["status"] = "standby"
            standby_count += 1

    # Advance the day clock
    today_dt = datetime.fromisoformat(state["day_start"])
    next_day_dt = today_dt + timedelta(days=1)
    next_day_iso = next_day_dt.isoformat()

    # Generate tomorrow's flights
    new_flights = _generate_next_day_flights(next_day_iso, long_haul_assignments, state["crew"])

    # Pre-roster long-haul returns with yesterday's crew
    pre_rostered = 0
    for f in new_flights:
        if f.get("prerostered_crew_ids"):
            f["assigned_crew_ids"] = list(f["prerostered_crew_ids"])
            # Mark those crew on duty
            for cid in f["assigned_crew_ids"]:
                cmem = next((c for c in state["crew"] if c["id"] == cid), None)
                if cmem:
                    cmem["status"] = "on_duty"
                    cmem["assigned_flight_id"] = f["id"]
            pre_rostered += 1
        f.pop("prerostered_crew_ids", None)

    # Roll state
    state["day_number"] = state.get("day_number", 1) + 1
    state["day_start"] = next_day_iso
    state["clock"] = next_day_iso
    state["flights"] = new_flights
    state["incidents"] = []
    state["decisions_log"] = []
    state["tick_count"] = 0
    state["phase"] = "ROSTER"
    state["kpis"] = {
        "otp_pct": 100.0,
        "legality_breaches": 0,
        "fatigue_index": int(sum(c["fatigue_score"] for c in state["crew"]) / max(1, len(state["crew"]))),
        "cost_usd": 0,
        "pax_delay_min": 0,
        "pax_disrupted": 0,
        "score": 1000,
    }
    return {
        "day_number": state["day_number"],
        "pre_rostered_returns": pre_rostered,
        "campaign_kpis": ck,
    }


def _generate_next_day_flights(day_start_iso: str, long_haul_returns: dict, crew_list: list[dict]) -> list[dict]:
    """Generate tomorrow's flights.
    `long_haul_returns` maps crew_id -> {station, origin, destination, block_min, aircraft_reg, aircraft_type}
    Returns list of flight dicts; long-haul returns have `prerostered_crew_ids` set so they're auto-assigned.
    """
    flights: list[dict] = []
    day_start = datetime.fromisoformat(day_start_iso)
    fnum = 200

    # Group long-haul returns by aircraft (the same aircraft brings the crew back)
    returns_by_reg: dict[str, dict] = {}
    crew_by_reg: dict[str, list[str]] = {}
    for cid, info in long_haul_returns.items():
        reg = info["aircraft_reg"]
        returns_by_reg[reg] = info
        crew_by_reg.setdefault(reg, []).append(cid)

    # Long-haul returns — depart from outstation early in the day (1-4h after day start)
    long_haul_regs_used: set[str] = set()
    for reg, info in returns_by_reg.items():
        depart_min = random.randint(60, 240)
        std = (day_start + timedelta(minutes=depart_min)).isoformat()
        sta = _add_minutes_to_clock(std, info["block_min"])
        pairing_id = _hash_id("PAIR")
        ac = {"reg": reg, "type": info["aircraft_type"]}
        f = _make_flight(fnum, info["origin"], info["destination"], std, sta, info["block_min"], ac, pairing_id)
        f["prerostered_crew_ids"] = crew_by_reg.get(reg, [])
        f["note"] = "RETURN FROM NIGHT-STOP · crew pre-rostered"
        flights.append(f)
        long_haul_regs_used.add(reg)
        fnum += 2

    # Short-haul: every A320 does new out-and-backs from LHR
    for ac in FLEET:
        if ac["type"] != "A320":
            continue
        depart_min = random.randint(0, 180)
        rotations = random.choice([2, 3])
        for _ in range(rotations):
            origin, dest, block = random.choice(ROUTES_SHORT)
            pairing_id = _hash_id("PAIR")
            std = (day_start + timedelta(minutes=depart_min)).isoformat()
            sta = _add_minutes_to_clock(std, block)
            flights.append(_make_flight(fnum, origin, dest, std, sta, block, ac, pairing_id))
            fnum += 2
            depart_min += block + 60
            std2 = (day_start + timedelta(minutes=depart_min)).isoformat()
            sta2 = _add_minutes_to_clock(std2, block)
            flights.append(_make_flight(fnum, dest, origin, std2, sta2, block, ac, pairing_id))
            fnum += 2
            depart_min += block + 60

    # Long-haul NEW outbounds: any LH aircraft NOT used for a return (i.e. it's at LHR)
    for ac in FLEET:
        if ac["type"] == "A320":
            continue
        if ac["reg"] in long_haul_regs_used:
            continue  # this aircraft is downroute returning, no new outbound today
        choices = [r for r in ROUTES_LONG if r[3] == ac["type"]]
        if not choices:
            continue
        origin, dest, block, _type_pref = random.choice(choices)
        depart_min = random.randint(0, 180)
        std = (day_start + timedelta(minutes=depart_min)).isoformat()
        sta = _add_minutes_to_clock(std, block)
        pairing_id = _hash_id("PAIR")
        flights.append(_make_flight(fnum, origin, dest, std, sta, block, ac, pairing_id))
        fnum += 2

    flights.sort(key=lambda f: f["std"])
    return flights


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

    # FDP — short-haul out-and-back pairing is ONE Flight Duty Period
    pairing_id = flight.get("pairing_id")
    pairing_flights = [f for f in state["flights"] if pairing_id and f.get("pairing_id") == pairing_id]
    if not pairing_flights:
        pairing_flights = [flight]
    pairing_block = sum(pf["block_min"] for pf in pairing_flights)
    # Add report (60min) + turnaround time(s) + post-flight (30min)
    pairing_sectors = len(pairing_flights)
    fdp_total = pairing_block + 60 + 30 + (pairing_sectors - 1) * 60  # 60-min turnaround per sector change
    projected_fdp = crew["fdp_used_min"] + fdp_total
    fdp_max, basis = _fdp_cap_for_flight(flight)
    if projected_fdp > fdp_max:
        warnings.append({
            "code": "FDP_EXCEED",
            "severity": "critical",
            "message": (
                f"Flight Duty Period for this pairing ({pairing_sectors} sector{'s' if pairing_sectors>1 else ''}, "
                f"{pairing_block//60}h{pairing_block%60:02d}m block) would reach "
                f"{projected_fdp//60}h{projected_fdp%60:02d}m, exceeding the maximum "
                f"{fdp_max//60}h FDP applicable ({basis})."
            ),
            "rule_ref": "ORO.FTL.205 / CS FTL.1.205",
        })

    # 28-day block hours (consider whole pairing)
    projected_28d = crew["block_28d_hr"] + (pairing_block / 60)
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
    """Assign a crew member to a flight. Returns {ok, warnings, breaches}.
    Short-haul out-and-back pairings: if this flight has siblings sharing
    `pairing_id`, the same crew is automatically rostered on the whole pairing
    (this is how real short-haul operates — crew operate out & back).
    """
    warnings = check_assignment(state, flight_id, crew_id)
    critical = [w for w in warnings if w["severity"] == "critical"]
    if critical and not force:
        return {"ok": False, "warnings": warnings, "applied": False}

    flight = next(f for f in state["flights"] if f["id"] == flight_id)
    crew = next(c for c in state["crew"] if c["id"] == crew_id)

    # All sectors in the same pairing — assign the crew to every sector
    pairing_id = flight.get("pairing_id")
    pairing_flights = [
        f for f in state["flights"]
        if pairing_id and f.get("pairing_id") == pairing_id
    ] or [flight]

    for pf in pairing_flights:
        if crew_id not in pf["assigned_crew_ids"]:
            pf["assigned_crew_ids"].append(crew_id)
    crew["assigned_flight_id"] = flight_id
    if crew["status"] not in ("standby", "off", "sick"):
        crew["status"] = "on_duty"

    if critical and force:
        state["kpis"]["legality_breaches"] += len(critical)
        state["kpis"]["score"] -= 80 * len(critical)
    return {
        "ok": True,
        "warnings": warnings,
        "applied": True,
        "pairing_sectors": len(pairing_flights),
    }


def unassign_crew(state: dict, flight_id: str, crew_id: str) -> dict:
    """Unassign a crew from a flight AND from any sibling sectors in the same
    pairing (short-haul out-and-back is a single duty)."""
    flight = next((f for f in state["flights"] if f["id"] == flight_id), None)
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not flight or not crew:
        return {"ok": False}
    pairing_id = flight.get("pairing_id")
    pairing_flights = [
        f for f in state["flights"]
        if pairing_id and f.get("pairing_id") == pairing_id
    ] or [flight]
    for pf in pairing_flights:
        if crew_id in pf["assigned_crew_ids"]:
            pf["assigned_crew_ids"].remove(crew_id)
    if crew["assigned_flight_id"] in [pf["id"] for pf in pairing_flights]:
        crew["assigned_flight_id"] = None
        if crew["status"] == "on_duty":
            crew["status"] = "available"
    return {"ok": True, "pairing_sectors": len(pairing_flights)}


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


# Survive-7 difficulty curve: per-tick max incidents weighted [0,1,2,3]
# Day 1 mild → Day 7 brutal. Used only in challenge mode.
SURVIVE_7_CURVE = {
    1: {"weights": [60, 30, 10, 0],  "weather_mult": 1.0, "tech_mult": 1.0, "sick_mult": 1.0},
    2: {"weights": [55, 32, 12, 1],  "weather_mult": 1.1, "tech_mult": 1.0, "sick_mult": 1.0},
    3: {"weights": [45, 35, 17, 3],  "weather_mult": 1.3, "tech_mult": 1.2, "sick_mult": 1.1},
    4: {"weights": [35, 38, 22, 5],  "weather_mult": 1.6, "tech_mult": 1.4, "sick_mult": 1.3},
    5: {"weights": [20, 35, 30, 15], "weather_mult": 2.2, "tech_mult": 1.6, "sick_mult": 1.5},
    6: {"weights": [15, 30, 35, 20], "weather_mult": 2.0, "tech_mult": 2.0, "sick_mult": 1.6},
    7: {"weights": [10, 25, 35, 30], "weather_mult": 1.8, "tech_mult": 2.5, "sick_mult": 1.8},
}


def tick(state: dict, minutes: int = 30) -> dict:
    """Advance the simulation clock by `minutes`. May spawn incidents."""
    if state["phase"] != "OPS":
        return {"ok": False, "reason": "Not in OPS phase"}
    state["tick_count"] += 1
    clock = datetime.fromisoformat(state["clock"]) + timedelta(minutes=minutes)
    state["clock"] = clock.isoformat()

    new_incidents = []
    # Spawn incidents per tick, weighted (challenge mode: escalates with day)
    if state.get("is_challenge"):
        day = state.get("day_number", 1)
        curve = SURVIVE_7_CURVE.get(day, SURVIVE_7_CURVE[7])
        weights = curve["weights"]
        type_weight_mult = {
            "CREW_SICK": curve["sick_mult"],
            "WEATHER": curve["weather_mult"],
            "TECH": curve["tech_mult"],
        }
        n = random.choices([0, 1, 2, 3], weights=weights)[0]
    else:
        n = random.choices([0, 1, 2], weights=[50, 35, 15])[0]
        type_weight_mult = {}
    for _ in range(n):
        adj_weights = [
            i[1] * type_weight_mult.get(i[0], 1.0)
            for i in INCIDENT_TYPES
        ]
        kind, _w, desc = random.choices(
            INCIDENT_TYPES,
            weights=adj_weights,
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
