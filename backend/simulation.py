"""
Airline Crew-Control Simulation Engine
=======================================
Domain model + EASA/UK CAA-inspired (simplified) rule checks.
NOTE: This is a SIMULATION for entertainment / training value only.
It is NOT an official compliance tool.
"""

from __future__ import annotations
import math
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

# Fleet: tail registrations. Tails flagged `spare` start the day on the ground
# with no scheduled flying — they are the fleet controller's reserve, available
# to swap onto a rotation (via the Aircraft Control desk) or to cover a tech
# aircraft. Non-spare tails each fly a generated set of rotations.
FLEET = [
    {"reg": "G-EAGA", "type": "A320"},
    {"reg": "G-EAGB", "type": "A320"},
    {"reg": "G-EAGC", "type": "A320"},
    {"reg": "G-EAGD", "type": "A320"},
    {"reg": "G-EAGL", "type": "A350"},
    {"reg": "G-EAGM", "type": "A350"},
    {"reg": "G-EAGN", "type": "B777"},
    {"reg": "G-EAGO", "type": "B777"},
    # Reserve aircraft (one per family) — on stand, ready to be assigned.
    {"reg": "G-EAGE", "type": "A320", "spare": True},
    {"reg": "G-EAGP", "type": "A350", "spare": True},
    {"reg": "G-EAGQ", "type": "B777", "spare": True},
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
MAX_DUTY_7D_MIN = MAX_DUTY_7D_HR * 60
MIN_TURNAROUND_MIN = 45          # minimum ground time before the same tail departs again
DIVERSION_RECOVERY_MIN = 120     # extra positioning time after a diversion before next sector
# LHR night curfew (simplified, inspired by real EGLL noise-abatement rules):
# movements at the hub between 23:00Z and 06:00Z draw a regulatory fine.
CURFEW_AIRPORT = "LHR"
CURFEW_START_HOUR = 23
CURFEW_END_HOUR = 6
CURFEW_FINE_BASE_USD = 6000
CURFEW_FINE_PER_PAX_USD = 8
# Recurrent days free of duty: crew may not operate beyond this many consecutive
# duty days without a day off; a warning is raised the day before the limit.
MAX_CONSECUTIVE_DUTY_DAYS = 6
DAYS_OFF_WARN_AT = MAX_CONSECUTIVE_DUTY_DAYS - 1
# Duty codes recorded per crew per day (roster line / calendar cells)
DUTY_FREE_CODES = ("OFF", "REST", "SICK")   # a day that resets the consecutive-duty count


def _fdp_cap_for_flight(flight: dict) -> tuple[int, str]:
    """Return (max_fdp_min, basis_str) for a flight given aircraft + crew complement."""
    ac_type = flight["aircraft_type"]
    block = flight["block_min"]
    if block <= 360:
        return MAX_FDP_MIN_2SECTOR, "short-haul, 2-sector acclimatised"
    # Long-haul
    rest_class = AIRCRAFT_TYPES.get(ac_type, {}).get("crew_rest_class", "none")
    req = flight.get("required_crew", {})
    # Augmentation is carried entirely by relief First Officers now (a single
    # Captain operates every sector — see _required_crew_for) — so "augmented"
    # means a relief pilot is rostered, i.e. FO count above the base of 1.
    augmented = req.get("FO", 1) >= 2
    if augmented and rest_class == "class_1":
        return MAX_FDP_MIN_LONGHAUL_BUNK, f"long-haul augmented crew + Class 1 bunks ({ac_type})"
    return MAX_FDP_MIN_LONGHAUL_BASE, f"long-haul ({ac_type}) without bunk/augment extension"

# ------------------- Helpers ------------------- #

def _hash_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------- Crew generation ------------------- #

def _seed_duty_history(days_since_off: int, length: int = 6) -> list[str]:
    """Synthesise a plausible recent roster line so the calendar is populated on
    day 1. The trailing run of duty codes equals `days_since_off` (kept consistent
    with the authoritative counter); a day off sits just before that streak."""
    duty_pool = ["FLT", "AVL", "FLT", "SBY"]
    hist: list[str] = []
    earlier = length - days_since_off
    for _ in range(max(0, earlier)):
        hist.append(random.choice(["FLT", "AVL", "OFF", "SBY", "FLT", "AVL"]))
    if earlier >= 1:
        hist[-1] = "OFF"   # the day-off that ended the previous streak
    for _ in range(min(days_since_off, length)):
        hist.append(random.choice(duty_pool))
    return hist[-length:]


RANK_TITLES = {"CP": "Captain", "FO": "First Officer", "SC": "Senior Cabin", "CC": "Cabin Crew"}
AIRCRAFT_TYPES_LIST = ["A320", "A350", "B777"]
# Headroom over expected daily slot demand: real crew bases run well beyond
# one day's minimum flying requirement to absorb standby, sickness, days-off
# and training — this is what keeps "start the day fully rostered" achievable
# without making disruption during ops toothless.
CREW_SUPPLY_BUFFER = 1.3


def _expected_daily_crew_demand() -> dict[tuple[str, str], float]:
    """Expected crew-slot demand per (rank, type), derived from the fleet and
    route-generation rules via _required_crew_for (single source of truth for
    crew composition — no duplicated headcount logic to drift out of sync).
    Not sampled from one game's random flights, so it stays stable across
    every day of a campaign. A320 rotation count and long-haul route choice
    are both randomised per aircraft per day — this averages over those
    distributions rather than assuming worst case, which would wildly
    over-provision the crew pool."""
    demand: dict[tuple[str, str], float] = {}

    def add(rank: str, t: str, n: float) -> None:
        demand[(rank, t)] = demand.get((rank, t), 0.0) + n

    # Spare tails don't fly a scheduled programme, so they generate no crew
    # demand — count only the active (non-spare) fleet.
    a320_count = sum(1 for ac in FLEET if ac["type"] == "A320" and not ac.get("spare"))
    if a320_count:
        avg_rotations = sum(range(2, 4)) / len(range(2, 4))  # random.choice([2, 3])
        req = _required_crew_for("A320", 0)  # block length doesn't affect A320 composition
        for rank in ("CP", "FO", "SC", "CC"):
            add(rank, "A320", a320_count * avg_rotations * req[rank])

    for t in ("A350", "B777"):
        fleet_count = sum(1 for ac in FLEET if ac["type"] == t and not ac.get("spare"))
        choices = [r for r in ROUTES_LONG if r[3] == t]
        if not fleet_count or not choices:
            continue
        for rank in ("CP", "FO", "SC", "CC"):
            avg_req = sum(_required_crew_for(t, r[2])[rank] for r in choices) / len(choices)
            add(rank, t, fleet_count * avg_req)

    return demand


def _make_crew(rank: str, quals: list[str], cid: int, used_names: set[str]) -> dict:
    for _try in range(50):
        surname = random.choice(CREW_NAMES)
        initial = random.choice("ABCDEFGHJKLMNPRSTW")
        disp = f"{initial}. {surname}"
        if disp not in used_names:
            used_names.add(disp)
            break
    dso = random.randint(0, 5)
    return {
        "id": f"EGW{cid}",
        "name": disp,
        "rank": rank,
        "rank_title": RANK_TITLES[rank],
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
        # ---- Days-off / roster-line tracking ----
        # consecutive duty days since the crew's last day free of duty
        "days_since_off": dso,
        # per-completed-day duty codes (oldest->newest), grows each day
        "duty_history": _seed_duty_history(dso),
        # absolute future day_numbers the controller has pre-marked OFF
        "days_off_planned": [],
    }


def _generate_crew() -> list[dict]:
    crew: list[dict] = []
    used_names: set[str] = set()
    cid = 1000

    def spawn(rank: str, quals: list[str]) -> None:
        nonlocal cid
        crew.append(_make_crew(rank, quals, cid, used_names))
        cid += 1

    # 1. Guaranteed floor: single-type-qualified crew sized off expected daily
    # demand per (rank, type), with buffer — guarantees the fleet's actual
    # workload is coverable by rank AND by type-rating, not just in aggregate.
    for (rank, t), qty in _expected_daily_crew_demand().items():
        for _ in range(math.ceil(qty * CREW_SUPPLY_BUFFER)):
            spawn(rank, [t])

    # 2. Extra variety pool: dual/tri-rated crew for flavour and additional
    # standby depth beyond the guaranteed floor. Flight deck are rarely
    # multi-rated in reality; cabin crew commonly are.
    extras = {"CP": 3, "FO": 5, "SC": 4, "CC": 8}
    for rank, n in extras.items():
        for _ in range(n):
            primary = random.choice(AIRCRAFT_TYPES_LIST)
            quals = [primary]
            dual_chance = 0.15 if rank in ("CP", "FO") else 0.5
            if random.random() < dual_chance:
                quals.append(random.choice([t for t in AIRCRAFT_TYPES_LIST if t != primary]))
            spawn(rank, quals)

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
        if ac.get("spare"):
            continue  # reserve tail — starts the day idle on stand
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


def _relief_pilots_for(block_min: int) -> int:
    """Extra flight-deck pilots for cruise relief on long sectors, modelled as
    additional First Officers rather than a separate rank — one relief pilot
    covers rest breaks up to ~12h, two beyond that. A single Captain operates
    every sector regardless of length; only the FO count scales."""
    if block_min <= 540:      # <= 9h: standard 2-pilot crew, no relief needed
        return 0
    if block_min < 720:       # 9-12h: one relief pilot (3-pilot flight deck)
        return 1
    return 2                  # 12h+: two relief pilots (4-pilot flight deck)


def _required_crew_for(ac_type: str, block_min: int) -> dict:
    """Standard airline crew composition: 1 Captain + 1 First Officer (plus
    relief pilots on long sectors), 1 inflight/cabin manager (plus 1 purser
    on long-haul), and 1 cabin crew member per 50 certified seats."""
    seats = AIRCRAFT_TYPES[ac_type]["seats"]
    cc = math.ceil(seats / 50)
    if ac_type == "A320":
        return {"CP": 1, "FO": 1, "SC": 1, "CC": cc, "type_qual": ac_type}
    return {
        "CP": 1,
        "FO": 1 + _relief_pilots_for(block_min),
        "SC": 2,  # inflight manager + purser
        "CC": cc,
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
            "curfew_violations": 0,
            "compensation_usd": 0,
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
    incoming_day = state.get("day_number", 1) + 1
    for c in state["crew"]:
        flown = today_block_by_crew.get(c["id"], 0)
        # Record the duty code for the day just completed (status still reflects
        # how the day was spent, before we reset it for tomorrow).
        if flown > 0:
            day_code = "FLT"
        elif c["status"] == "off":
            day_code = "OFF"
        elif c["status"] == "sick":
            day_code = "SICK"
        elif c["status"] == "standby":
            day_code = "SBY"
        else:
            day_code = "AVL"   # available reserve — still a duty day, not a day off
        c.setdefault("duty_history", []).append(day_code)
        if len(c["duty_history"]) > 28:
            c["duty_history"] = c["duty_history"][-28:]
        # Consecutive-duty counter: a day free of duty resets it, anything else adds
        if day_code in DUTY_FREE_CODES:
            c["days_since_off"] = 0
        else:
            c["days_since_off"] = c.get("days_since_off", 0) + 1
            # Auto-plan tomorrow off once the consecutive-duty cap is reached.
            # Real crew-rostering software bakes legal rest days into the
            # baseline roster line rather than leaving compliance to be
            # remembered manually — the controller can still override via
            # the Days-Off calendar (set_day_off) if operational need demands
            # it, same as commander's/rostering discretion in practice.
            if c["days_since_off"] >= MAX_CONSECUTIVE_DUTY_DAYS:
                planned = c.setdefault("days_off_planned", [])
                if incoming_day not in planned:
                    planned.append(incoming_day)

        c.setdefault("block_history", [])
        c["block_history"].append(flown)
        # keep sliding window of last 28 days
        if len(c["block_history"]) > 28:
            c["block_history"] = c["block_history"][-28:]
        c["block_28d_hr"] = round(sum(c["block_history"]), 1)
        # duty_7d_hr must be a ROLLING 7-day sum, not a running total — it's
        # incremented intraday in tick() as flights land (so same-day legality
        # checks see hours flown so far today), but nothing was ever rolling
        # the oldest day back out. Left unfixed, every active crew member
        # marches past the 60h/7-day cap by day 3-4 and never returns,
        # collapsing roster feasibility for the rest of the campaign.
        c["duty_7d_hr"] = round(sum(c["block_history"][-7:]), 2)
        c["fdp_used_min"] = 0
        # Fatigue update — a day off recovers more than an idle reserve day
        if flown > 0:
            c["fatigue_score"] = min(100, c["fatigue_score"] + random.randint(8, 18))
        elif day_code == "OFF":
            c["fatigue_score"] = max(5, c["fatigue_score"] - random.randint(12, 22))
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
        # Honour a pre-planned day off for the incoming day (wins over the reset
        # above, and keeps the crew out of the standby pool re-draw below).
        if incoming_day in c.get("days_off_planned", []):
            c["status"] = "off"
            c["assigned_flight_id"] = None
            c["days_off_planned"] = [d for d in c["days_off_planned"] if d != incoming_day]

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
        "curfew_violations": 0,
        "compensation_usd": 0,
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

    # 7-day duty hours
    pairing_duty_hr = fdp_total / 60
    projected_7d = crew.get("duty_7d_hr", 0) + pairing_duty_hr
    if projected_7d > MAX_DUTY_7D_HR:
        warnings.append({
            "code": "DUTY_7D",
            "severity": "critical",
            "message": (
                f"Projected 7-day duty = {projected_7d:.1f}h, exceeds the {MAX_DUTY_7D_HR}h weekly limit. "
                f"Current accumulation: {crew.get('duty_7d_hr', 0):.1f}h."
            ),
            "rule_ref": "ORO.FTL.210(a) — 60h duty in 7 consecutive days",
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

    # Recurrent days free of duty — operating today adds another consecutive
    # duty day. Beyond the limit the crew is owed a statutory day off first.
    dso = crew.get("days_since_off", 0)
    if dso >= MAX_CONSECUTIVE_DUTY_DAYS:
        warnings.append({
            "code": "DAYS_OFF_REQUIRED",
            "severity": "critical",
            "message": (
                f"Crew {crew['id']} has worked {dso} consecutive duty days. A day free of "
                f"duty is required before further rostering (max {MAX_CONSECUTIVE_DUTY_DAYS})."
            ),
            "rule_ref": "ORO.FTL.235(d) — Recurrent days free of duty",
        })
    elif dso >= DAYS_OFF_WARN_AT:
        warnings.append({
            "code": "DAYS_OFF_DUE",
            "severity": "warning",
            "message": (
                f"Crew {crew['id']} is on consecutive duty day {dso}. Roster a day off within "
                f"{MAX_CONSECUTIVE_DUTY_DAYS - dso} day(s) to stay legal."
            ),
            "rule_ref": "ORO.FTL.235(d) — Recurrent days free of duty",
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


# ------------------- Crew roster line / days off ------------------- #

def _today_duty_code(state: dict, crew: dict) -> str:
    """Live duty code for the current operational day (calendar 'today' cell)."""
    if crew.get("status") == "sick":
        return "SICK"
    cid = crew["id"]
    if any(cid in f["assigned_crew_ids"] for f in state["flights"]):
        return "FLT"
    st = crew.get("status")
    if st == "off":
        return "OFF"
    if st == "standby":
        return "SBY"
    return "AVL"   # available reserve / open


def crew_roster(state: dict, past_days: int = 5, future_days: int = 4) -> dict:
    """Build the AerOPS-style crew calendar: one row per crew, one cell per day.
    Past cells come from the recorded duty_history, today is live, future cells
    show planned days off (anything else is open)."""
    day_number = state.get("day_number", 1)
    days = list(range(day_number - past_days, day_number + future_days + 1))
    base_date = datetime.fromisoformat(state["day_start"]).date()
    columns = [{
        "day": d,
        "date": (base_date + timedelta(days=d - day_number)).isoformat(),
        "is_today": d == day_number,
        "is_future": d > day_number,
        "is_past": d < day_number,
    } for d in days]
    rows = []
    for c in state["crew"]:
        hist = c.get("duty_history", [])
        planned = set(c.get("days_off_planned", []))
        dso = c.get("days_since_off", 0)
        cells = []
        for d in days:
            if d < day_number:
                offset = day_number - d            # 1 == yesterday
                code = hist[-offset] if offset <= len(hist) else None
                cells.append({"day": d, "code": code, "rel": "past"})
            elif d == day_number:
                cells.append({"day": d, "code": _today_duty_code(state, c), "rel": "today"})
            else:
                cells.append({
                    "day": d,
                    "code": "OFF" if d in planned else None,
                    "rel": "future",
                    "planned_off": d in planned,
                })
        rows.append({
            "crew_id": c["id"],
            "name": c["name"],
            "rank": c["rank"],
            "rank_title": c.get("rank_title", ""),
            "base": c.get("base", "LHR"),
            "qualifications": c.get("qualifications", []),
            "status": c.get("status"),
            "days_since_off": dso,
            "fatigue_score": c.get("fatigue_score", 0),
            "due_off": dso >= DAYS_OFF_WARN_AT,
            "at_limit": dso >= MAX_CONSECUTIVE_DUTY_DAYS,
            "cells": cells,
        })
    return {
        "day_number": day_number,
        "days": days,
        "columns": columns,
        "past_days": past_days,
        "future_days": future_days,
        "max_consecutive_duty_days": MAX_CONSECUTIVE_DUTY_DAYS,
        "warn_at": DAYS_OFF_WARN_AT,
        "crew": rows,
    }


def set_day_off(state: dict, crew_id: str, day: int, off: bool = True) -> dict:
    """Toggle a day off for a crew member. Future days are queued in
    days_off_planned (honoured when the sim rolls into that day). The current day
    can only be changed during the ROSTER phase (before the day starts)."""
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not crew:
        return {"ok": False, "error": "crew_not_found"}
    day_number = state.get("day_number", 1)
    if day < day_number:
        return {"ok": False, "error": "cannot_change_past"}
    planned = crew.setdefault("days_off_planned", [])

    if day == day_number:
        if state.get("phase") != "ROSTER":
            return {"ok": False, "error": "day_in_progress"}
        if off:
            for f in state["flights"]:
                if crew_id in f["assigned_crew_ids"]:
                    f["assigned_crew_ids"].remove(crew_id)
            crew["assigned_flight_id"] = None
            crew["status"] = "off"
        elif crew["status"] == "off":
            crew["status"] = "available"
        return {
            "ok": True, "crew_id": crew_id, "day": day, "off": off,
            "status": crew["status"], "days_off_planned": planned,
        }

    # Future day
    if off and day not in planned:
        planned.append(day)
        planned.sort()
    elif not off and day in planned:
        planned.remove(day)
    return {
        "ok": True, "crew_id": crew_id, "day": day, "off": off,
        "days_off_planned": planned,
    }


# ------------------- Auto-roster ------------------- #

def auto_roster(state: dict) -> dict:
    """Greedy auto-assignment: fill all crew gaps without legality violations.
    Processes each flight, each rank gap, picking the lowest-fatigue qualified
    available/standby crew that passes a full legality check.
    Returns counts of assigned slots, skipped slots, and which flights changed.
    """
    assigned_total = 0
    skipped_total = 0
    flights_touched: list[str] = []

    # Collect pairing ids already processed so we don't double-count sibling sectors
    processed_pairings: set[str] = set()

    for flight in state["flights"]:
        pid = flight.get("pairing_id")
        if pid and pid in processed_pairings:
            continue

        req = flight["required_crew"]
        type_q = req["type_qual"]

        # Aggregate assigned ranks across all pairing sectors
        pairing_flights = (
            [f for f in state["flights"] if f.get("pairing_id") == pid]
            if pid else [flight]
        )
        rank_counts: dict[str, int] = {"CP": 0, "FO": 0, "SC": 0, "CC": 0}
        all_assigned_ids: set[str] = set()
        for pf in pairing_flights:
            for cid in pf["assigned_crew_ids"]:
                all_assigned_ids.add(cid)
        for cid in all_assigned_ids:
            c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
            if c and c["rank"] in rank_counts:
                rank_counts[c["rank"]] += 1

        flight_changed = False
        for rank in ("CP", "FO", "SC", "CC"):
            gap = req[rank] - rank_counts[rank]
            for _ in range(gap):
                candidates = [
                    c for c in state["crew"]
                    if c["rank"] == rank
                    and type_q in c["qualifications"]
                    and c["status"] in ("available", "standby")
                    and c["id"] not in all_assigned_ids
                ]
                # Prefer lowest fatigue, then most rested
                candidates.sort(key=lambda c: (c["fatigue_score"], -c["rest_hr_since_duty"]))

                placed = False
                for candidate in candidates:
                    warnings = check_assignment(state, flight["id"], candidate["id"])
                    if not any(w["severity"] == "critical" for w in warnings):
                        # Assign across all pairing sectors
                        for pf in pairing_flights:
                            if candidate["id"] not in pf["assigned_crew_ids"]:
                                pf["assigned_crew_ids"].append(candidate["id"])
                        candidate["assigned_flight_id"] = flight["id"]
                        if candidate["status"] not in ("off", "sick"):
                            candidate["status"] = "on_duty"
                        all_assigned_ids.add(candidate["id"])
                        rank_counts[rank] += 1
                        assigned_total += 1
                        flight_changed = True
                        placed = True
                        break
                if not placed:
                    skipped_total += 1

        if flight_changed and flight["callsign"] not in flights_touched:
            flights_touched.append(flight["callsign"])
        if pid:
            processed_pairings.add(pid)

    return {
        "assigned": assigned_total,
        "skipped": skipped_total,
        "flights_touched": flights_touched,
    }


# ------------------- Aircraft (fleet) control ------------------- #
# The real-world "Aircraft Movement Control" desk: which tail flies which
# rotation. A rotation is a pairing (all sectors sharing a pairing_id — an
# out-and-back for short-haul, a single sector for long-haul). Every sector of
# a pairing is always operated by the SAME tail, so assignment happens at the
# pairing level, mirroring how crew are rostered per pairing.

_AC_ACTIVE_STATUSES = ("scheduled", "delayed", "boarding")


def _pairing_sectors(state: dict, pairing_id: str) -> list[dict]:
    """All sector flights of a pairing, in schedule order."""
    return sorted(
        (f for f in state["flights"] if f.get("pairing_id") == pairing_id),
        key=lambda f: f["std"],
    )


def _pairing_window(sectors: list[dict]) -> tuple[datetime, datetime]:
    """(earliest effective departure, latest effective arrival) for a pairing,
    including any delay already applied — the ground-to-ground span the tail is
    committed for."""
    first = min(datetime.fromisoformat(s["std"]) + timedelta(minutes=s.get("delay_min", 0))
                for s in sectors)
    last = max(datetime.fromisoformat(s["sta"]) + timedelta(minutes=s.get("delay_min", 0))
               for s in sectors)
    return first, last


def _pairing_route_label(sectors: list[dict]) -> str:
    """Human route summary, e.g. 'LHR-BCN-LHR' or 'LHR-SIN'."""
    stops = [sectors[0]["origin"]] + [s["destination"] for s in sectors]
    return "-".join(stops)


def check_aircraft_assignment(state: dict, pairing_id: str, reg: str) -> list[dict]:
    """Legality of putting tail `reg` on a pairing. Aircraft constraints are
    HARD (a physical aircraft cannot be the wrong type, be in two places, or
    un-fly a sector already underway) — there is no override, unlike crew."""
    warnings: list[dict] = []
    sectors = _pairing_sectors(state, pairing_id)
    ac = next((a for a in state.get("fleet", FLEET) if a["reg"] == reg), None)
    if not sectors or not ac:
        return [{
            "code": "REF_NOT_FOUND", "severity": "critical",
            "message": "Aircraft or rotation reference not found.", "rule_ref": "INTERNAL",
        }]

    pairing_type = sectors[0]["aircraft_type"]
    if ac["type"] != pairing_type:
        warnings.append({
            "code": "AC_TYPE_MISMATCH", "severity": "critical",
            "message": (
                f"{reg} is a {ac['type']}; this rotation needs a {pairing_type}. "
                f"Crew type-ratings and gate/route planning are type-specific."
            ),
            "rule_ref": "Fleet / type compatibility",
        })

    # A sector already underway or finished can't be re-tailed.
    departed = [s for s in sectors if s["status"] not in _AC_ACTIVE_STATUSES]
    if departed:
        warnings.append({
            "code": "AC_DEPARTED", "severity": "critical",
            "message": (
                f"{departed[0]['callsign']} is already {departed[0]['status']} — "
                f"the rotation is underway and cannot be reassigned to another tail."
            ),
            "rule_ref": "Operational — sector in progress",
        })

    # Double-booking: the tail can't be committed to an overlapping rotation.
    if ac["type"] == pairing_type:
        win_start, win_end = _pairing_window(sectors)
        turn = timedelta(minutes=MIN_TURNAROUND_MIN)
        other_pairings: dict[str, list[dict]] = {}
        for f in state["flights"]:
            opid = f.get("pairing_id")
            if opid and opid != pairing_id and f["aircraft_reg"] == reg \
                    and f["status"] != "cancelled":
                other_pairings.setdefault(opid, []).append(f)
        for opid, osecs in other_pairings.items():
            o_start, o_end = _pairing_window(osecs)
            # Conflict unless one finishes (+turnaround) before the other starts.
            if not (win_end + turn <= o_start or o_end + turn <= win_start):
                osecs_sorted = sorted(osecs, key=lambda f: f["std"])
                warnings.append({
                    "code": "AC_OVERLAP", "severity": "critical",
                    "message": (
                        f"{reg} is already committed to {osecs_sorted[0]['callsign']} "
                        f"({_pairing_route_label(osecs_sorted)}), which overlaps this "
                        f"rotation's ground-time (min {MIN_TURNAROUND_MIN}min turnaround)."
                    ),
                    "rule_ref": "Operational — aircraft double-booking",
                })
                break
    return warnings


def assign_aircraft(state: dict, pairing_id: str, reg: str) -> dict:
    """Assign tail `reg` to every sector of a pairing. Hard constraints only —
    a critical warning blocks the change (no force path)."""
    warnings = check_aircraft_assignment(state, pairing_id, reg)
    if any(w["severity"] == "critical" for w in warnings):
        return {"ok": False, "applied": False, "warnings": warnings,
                "pairing_id": pairing_id, "reg": reg}

    sectors = _pairing_sectors(state, pairing_id)
    previous = sectors[0]["aircraft_reg"] if sectors else None
    for s in sectors:
        s["aircraft_reg"] = reg
    return {
        "ok": True, "applied": True, "warnings": warnings,
        "pairing_id": pairing_id, "reg": reg, "previous_reg": previous,
    }


def aircraft_control(state: dict) -> dict:
    """Fleet-control view: every tail with its rotations for the day, plus a
    per-rotation list for the reassignment table."""
    fleet = state.get("fleet", FLEET)

    # Group flights into pairings once.
    pairings: dict[str, list[dict]] = {}
    for f in state["flights"]:
        pid = f.get("pairing_id")
        if pid:
            pairings.setdefault(pid, []).append(f)
    for pid in pairings:
        pairings[pid].sort(key=lambda f: f["std"])

    def _pairing_status(secs: list[dict]) -> str:
        statuses = {s["status"] for s in secs}
        if statuses <= {"cancelled"}:
            return "cancelled"
        if "airborne" in statuses:
            return "airborne"
        if all(s["status"] == "landed" for s in secs):
            return "landed"
        if "boarding" in statuses:
            return "boarding"
        if any(s.get("delay_min", 0) > 15 for s in secs):
            return "delayed"
        return "scheduled"

    rotations = []
    by_reg_rotations: dict[str, list[dict]] = {}
    for pid, secs in pairings.items():
        first, last = _pairing_window(secs)
        rot = {
            "pairing_id": pid,
            "aircraft_reg": secs[0]["aircraft_reg"],
            "aircraft_type": secs[0]["aircraft_type"],
            "callsigns": [s["callsign"] for s in secs],
            "route": _pairing_route_label(secs),
            "sectors": len(secs),
            "std": secs[0]["std"],
            "sta": secs[-1]["sta"],
            "first_dep": first.isoformat(),
            "last_arr": last.isoformat(),
            "block_min": sum(s["block_min"] for s in secs),
            "pax": sum(s.get("pax_count", 0) for s in secs),
            "status": _pairing_status(secs),
            "reassignable": all(s["status"] in _AC_ACTIVE_STATUSES for s in secs),
        }
        rotations.append(rot)
        by_reg_rotations.setdefault(secs[0]["aircraft_reg"], []).append(rot)
    rotations.sort(key=lambda r: r["std"])

    fleet_view = []
    for ac in fleet:
        rots = sorted(by_reg_rotations.get(ac["reg"], []), key=lambda r: r["std"])
        block = sum(r["block_min"] for r in rots)
        if not rots:
            status = "spare" if ac.get("spare") else "idle"
        elif all(r["status"] == "landed" for r in rots):
            status = "day done"
        elif any(r["status"] == "airborne" for r in rots):
            status = "airborne"
        elif any(r["status"] == "delayed" for r in rots):
            status = "delayed"
        else:
            status = "in service"
        fleet_view.append({
            "reg": ac["reg"],
            "type": ac["type"],
            "spare": bool(ac.get("spare")),
            "rotation_count": len(rots),
            "sectors": sum(r["sectors"] for r in rots),
            "block_min": block,
            "block_hours": round(block / 60, 1),
            "status": status,
            "rotations": rots,
        })

    return {
        "fleet": fleet_view,
        "rotations": rotations,
        "min_turnaround_min": MIN_TURNAROUND_MIN,
    }


# ------------------- Day-of-Ops simulation ------------------- #

# Type weights informed by real delay-cause data (US DOT/BTS Air Travel
# Consumer Report; Eurocontrol CODA). Of the delay actually attributable to a
# single flight's own disruption (i.e. excluding reactionary/knock-on delay,
# which is the single largest real cause at 46-48% of delay minutes per
# Eurocontrol and is already modelled separately by
# propagate_reactionary_delays), the remainder splits roughly evenly across
# airline-internal causes (crew + technical/maintenance, ~31% of delayed
# flights per BTS), ATC/airspace-system causes (~31%), and weather (smaller
# in BTS's narrow "extreme weather" bucket, but weather's true footprint is
# much larger once its contribution to ATC-flow and reactionary delay is
# included — CODA and FAA both attribute a majority of NAS delay to weather
# at the root). The previous weights over-indexed on crew-specific causes
# relative to this evidence.
INCIDENT_TYPES = [
    ("CREW_SICK", 0.15, "Crew reported sick before report time."),
    ("LATE_REPORT", 0.10, "Crew running late for report."),
    ("WEATHER", 0.25, "Weather disruption at destination."),
    ("TECH", 0.25, "Technical defect / MEL deferral on aircraft."),
    ("ATC_FLOW", 0.25, "ATC slot / flow restriction imposed."),
]

# A real OCC is a room of specialist desks (Duty Ops Manager, Flight Dispatch,
# Crew Control, Maintenance Control, network/ATC liaison) and every delay is
# logged under a standard two-digit IATA delay code. Incidents carry both: the
# desk that raised them and the code the delay would be filed under.
#   63 late/absent crew · 64 crew shortage · 41 aircraft defect
#   72 destination weather · 81 ATFM/ATC en-route restriction · 93 reactionary
INCIDENT_META = {
    "CREW_SICK":   {"desk": "CREW CONTROL", "delay_code": "64"},
    "LATE_REPORT": {"desk": "CREW CONTROL", "delay_code": "63"},
    "TECH":        {"desk": "MX CONTROL",   "delay_code": "41"},
    "WEATHER":     {"desk": "DISPATCH",     "delay_code": "72"},
    "ATC_FLOW":    {"desk": "NETWORK/ATC",  "delay_code": "81"},
}

# The operation never pauses for a problem — but a problem you sit on gets
# worse. An open incident left unattended this long escalates: severity goes
# major, the flight takes further delay, and the recovery menu is re-priced
# from the (worse) live state. This replaces the old forced clock-pause with
# the time pressure a real duty controller actually faces.
ESCALATION_AFTER_MIN = 60
ESCALATION_EXTRA_DELAY_MIN = 30

# EU261/UK261-style passenger compensation: due when a flight ARRIVES 3h+
# late, per passenger, scaled by haul — UNLESS the root cause is an
# "extraordinary circumstance" outside the airline's control (weather, ATC),
# mirroring the real regulation. This is what makes delay-vs-cancel a genuine
# economic decision in a real OCC.
COMP_ARR_DELAY_THRESHOLD_MIN = 180
COMP_SHORT_HAUL_USD = 250   # ≈ £220 per pax
COMP_LONG_HAUL_USD = 600    # ≈ £520 per pax
COMP_EXEMPT_INCIDENT_TYPES = ("WEATHER", "ATC_FLOW")

# Expected NEW (primary) incidents per sim-hour of active ops. Deliberately
# calibrated well above the bare real-world rate (BTS/CODA data implies
# roughly 2-4 primary-cause disruptions across an average ~20-25 flight day)
# for pacing — this is a "hardcore" simulation, not a punctuality replica —
# but a fraction of the previous per-tick rate, which scaled with the NUMBER
# of tick() calls rather than elapsed time and so produced wildly more
# incidents at fine tick granularity (e.g. +5M ticks) than coarse (+60M).
BASE_INCIDENT_RATE_PER_HOUR = 0.4  # ~6-8 primary incidents across a full ops day

# Survive-7 difficulty curve: a rate MULTIPLIER on BASE_INCIDENT_RATE_PER_HOUR
# (day 1 mild -> day 7 brutal), preserving the shape of the original per-tick
# weight tables but expressed as a continuous rate so it composes correctly
# with Poisson sampling over arbitrary tick lengths. Used only in challenge mode.
SURVIVE_7_CURVE = {
    1: {"rate_mult": 1.0, "weather_mult": 1.0, "tech_mult": 1.0, "sick_mult": 1.0},
    2: {"rate_mult": 1.2, "weather_mult": 1.1, "tech_mult": 1.0, "sick_mult": 1.0},
    3: {"rate_mult": 1.55, "weather_mult": 1.3, "tech_mult": 1.2, "sick_mult": 1.1},
    4: {"rate_mult": 1.95, "weather_mult": 1.6, "tech_mult": 1.4, "sick_mult": 1.3},
    5: {"rate_mult": 2.8, "weather_mult": 2.2, "tech_mult": 1.6, "sick_mult": 1.5},
    6: {"rate_mult": 3.2, "weather_mult": 2.0, "tech_mult": 2.0, "sick_mult": 1.6},
    7: {"rate_mult": 3.7, "weather_mult": 1.8, "tech_mult": 2.5, "sick_mult": 1.8},
}


def _poisson_sample(lam: float, cap: int = 4) -> int:
    """Sample an event count from a Poisson distribution (Knuth's algorithm —
    no numpy dependency), capped to keep any single tick from spawning an
    unreasonable pile-up. `lam` is the expected count for this interval."""
    if lam <= 0:
        return 0
    limit = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= limit:
            return min(k - 1, cap)


def _in_curfew_window(dt: datetime) -> bool:
    """True if `dt` (any timezone-aware instant, compared by its hour) falls
    inside the LHR night curfew window, which wraps midnight."""
    h = dt.hour
    return h >= CURFEW_START_HOUR or h < CURFEW_END_HOUR


def _apply_curfew_violation(state: dict, flight: dict, kind: str) -> dict:
    """Record a curfew breach on `flight` (kind: 'departure' | 'arrival'),
    fine the operation, and return the violation record for the caller."""
    fine = CURFEW_FINE_BASE_USD + flight.get("pax_count", 0) * CURFEW_FINE_PER_PAX_USD
    state["kpis"]["curfew_violations"] = state["kpis"].get("curfew_violations", 0) + 1
    state["kpis"]["cost_usd"] += fine
    tag = f"LHR NIGHT CURFEW ({kind})"
    note = flight.get("note") or ""
    flight["note"] = f"{note} · {tag}" if note else tag
    flight["curfew_violation"] = kind
    return {
        "flight_id": flight["id"],
        "callsign": flight["callsign"],
        "kind": kind,
        "fine_usd": fine,
    }


def _maybe_charge_compensation(state: dict, flight: dict) -> dict | None:
    """EU261/UK261-style passenger compensation, assessed once when a flight
    lands: 3h+ arrival delay owes per-pax compensation scaled by haul, unless
    the flight was hit by an extraordinary-circumstances cause (weather/ATC),
    which exempts the airline — exactly the calculus a real OCC runs when
    weighing an airline-controllable delay against a cancellation."""
    if flight.get("comp_charged") or flight.get("comp_exempt"):
        return None
    if flight.get("delay_min", 0) < COMP_ARR_DELAY_THRESHOLD_MIN:
        return None
    rate = COMP_LONG_HAUL_USD if flight["block_min"] > 360 else COMP_SHORT_HAUL_USD
    amount = rate * flight.get("pax_count", 0)
    flight["comp_charged"] = True
    state["kpis"]["compensation_usd"] = state["kpis"].get("compensation_usd", 0) + amount
    state["kpis"]["cost_usd"] += amount
    note = flight.get("note") or ""
    tag = "EU261 COMP DUE"
    flight["note"] = f"{note} · {tag}" if note else tag
    return {
        "flight_id": flight["id"],
        "callsign": flight["callsign"],
        "amount_usd": amount,
        "pax": flight.get("pax_count", 0),
    }


def tick(state: dict, minutes: int = 30) -> dict:
    """Advance the simulation clock by `minutes`. May spawn incidents."""
    if state["phase"] != "OPS":
        return {"ok": False, "reason": "Not in OPS phase"}
    state["tick_count"] += 1
    clock = datetime.fromisoformat(state["clock"]) + timedelta(minutes=minutes)
    state["clock"] = clock.isoformat()

    # ---- Flight lifecycle progression ----
    curfew_violations = []
    comp_events = []
    for f in state["flights"]:
        if f["status"] in ("cancelled", "diverted", "landed"):
            continue
        delay = f.get("delay_min", 0)
        std_dt = datetime.fromisoformat(f["std"]) + timedelta(minutes=delay)
        sta_dt = datetime.fromisoformat(f["sta"]) + timedelta(minutes=delay)

        # Curfew is checked once, at the first tick the effective time is
        # crossed — decoupled from the status label so a delay-inflated
        # departure/arrival still gets caught even if status stalls at
        # "boarding" rather than flipping to "airborne".
        if clock >= std_dt and not f.get("curfew_dep_checked"):
            f["curfew_dep_checked"] = True
            if f["origin"] == CURFEW_AIRPORT and _in_curfew_window(std_dt):
                curfew_violations.append(_apply_curfew_violation(state, f, "departure"))
        if clock >= sta_dt and not f.get("curfew_arr_checked"):
            f["curfew_arr_checked"] = True
            if f["destination"] == CURFEW_AIRPORT and _in_curfew_window(sta_dt):
                curfew_violations.append(_apply_curfew_violation(state, f, "arrival"))

        if clock >= sta_dt:
            prev = f["status"]
            f["status"] = "landed"
            # Accumulate FDP for crew on this flight when it lands
            if prev != "landed":
                comp = _maybe_charge_compensation(state, f)
                if comp:
                    comp_events.append(comp)
                for cid in f["assigned_crew_ids"]:
                    c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
                    if c:
                        c["fdp_used_min"] = c.get("fdp_used_min", 0) + f["block_min"]
                        c["duty_7d_hr"] = round(
                            c.get("duty_7d_hr", 0) + f["block_min"] / 60, 2
                        )
                        if c["status"] == "on_duty":
                            c["status"] = "available"
                        c["assigned_flight_id"] = None
        elif clock >= std_dt:
            if f["status"] not in ("airborne", "boarding"):
                f["status"] = "airborne"
        elif clock >= std_dt - timedelta(minutes=30):
            if f["status"] == "scheduled":
                f["status"] = "boarding"

    new_incidents = []
    # Spawn incidents at a rate scaled by elapsed sim-time (not by number of
    # tick() calls — a flat per-tick chance made incident count depend on how
    # finely the player ticked, e.g. far more incidents/day at +5M than +60M
    # for the same span of ops). Challenge mode escalates the rate with day.
    if state.get("is_challenge"):
        day = state.get("day_number", 1)
        curve = SURVIVE_7_CURVE.get(day, SURVIVE_7_CURVE[7])
        rate_mult = curve["rate_mult"]
        type_weight_mult = {
            "CREW_SICK": curve["sick_mult"],
            "WEATHER": curve["weather_mult"],
            "TECH": curve["tech_mult"],
        }
    else:
        rate_mult = 1.0
        type_weight_mult = {}
    lam = BASE_INCIDENT_RATE_PER_HOUR * rate_mult * (minutes / 60.0)
    n = _poisson_sample(lam)
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
        meta = INCIDENT_META.get(kind, {})
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
            "options": [],
            "reported_by": meta.get("desk"),
            "delay_code": meta.get("delay_code"),
            "escalated": False,
        }
        # Weather/ATC are "extraordinary circumstances" under EU261/UK261 —
        # a flight disrupted by them owes no passenger compensation however
        # late it eventually arrives.
        if kind in COMP_EXEMPT_INCIDENT_TYPES:
            flight["comp_exempt"] = True
        # Apply immediate impact
        if kind == "CREW_SICK" and flight["assigned_crew_ids"]:
            # mark one assigned crew as sick — off the whole pairing (one duty)
            cid = random.choice(flight["assigned_crew_ids"])
            c = next(cc for cc in state["crew"] if cc["id"] == cid)
            c["status"] = "sick"
            c["assigned_flight_id"] = None
            pairing_id = flight.get("pairing_id")
            for pf in state["flights"]:
                if (pf["id"] == flight["id"] or (pairing_id and pf.get("pairing_id") == pairing_id)) \
                        and cid in pf["assigned_crew_ids"]:
                    pf["assigned_crew_ids"].remove(cid)
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

        # Options are computed AFTER the impact so they see the real gap
        inc["options"] = _recovery_options_for(state, flight, kind, sev)

        new_incidents.append(inc)
        state["incidents"].append(inc)

    # ---- Escalate unattended incidents (the price of not deciding) ----
    escalations = []
    for inc in state["incidents"]:
        if inc["status"] != "open" or inc.get("escalated"):
            continue
        raised = datetime.fromisoformat(inc["raised_at"])
        if (clock - raised).total_seconds() / 60 < ESCALATION_AFTER_MIN:
            continue
        fl = next((f for f in state["flights"] if f["id"] == inc["flight_id"]), None)
        if not fl or fl["status"] not in ("scheduled", "delayed", "boarding"):
            continue  # overtaken by events — nothing left to escalate into
        inc["escalated"] = True
        inc["severity"] = "major"
        fl["delay_min"] += ESCALATION_EXTRA_DELAY_MIN
        if fl["status"] == "scheduled":
            fl["status"] = "delayed"
        # Re-price the menu from the now-worse live state (major severity also
        # closes doors, e.g. MEL deferral is minor-only).
        inc["options"] = _recovery_options_for(state, fl, inc["type"], "major")
        inc["escalation_note"] = (
            f"Unattended {ESCALATION_AFTER_MIN}min — severity raised to MAJOR, "
            f"{fl['callsign']} +{ESCALATION_EXTRA_DELAY_MIN}min"
        )
        escalations.append({
            "incident_id": inc["id"],
            "flight_callsign": fl["callsign"],
            "added_min": ESCALATION_EXTRA_DELAY_MIN,
        })

    reactionary = propagate_reactionary_delays(state)
    _recompute_kpis(state)
    return {
        "ok": True,
        "new_incidents": new_incidents,
        "reactionary_delays": reactionary,
        "curfew_violations": curfew_violations,
        "escalations": escalations,
        "compensation_events": comp_events,
        "clock": state["clock"],
    }


def _missing_ranks(state: dict, flight: dict) -> list[str]:
    """Ranks (in seniority order) where the flight is short of required crew."""
    req = flight["required_crew"]
    counts = {"CP": 0, "FO": 0, "SC": 0, "CC": 0}
    for cid in flight["assigned_crew_ids"]:
        c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
        if c:
            counts[c["rank"]] += 1
    return [r for r in ("CP", "FO", "SC", "CC") if counts[r] < req[r]]


def _legal_candidates(state: dict, flight: dict, rank: str, statuses: tuple[str, ...]) -> list[dict]:
    """Crew of `rank` in one of `statuses`, type-rated for the flight, passing a
    full legality check. Sorted by fatigue (freshest first)."""
    type_q = flight["required_crew"]["type_qual"]
    out = []
    for c in state["crew"]:
        if c["rank"] != rank or c["status"] not in statuses:
            continue
        if type_q not in c["qualifications"]:
            continue
        if any(w["severity"] == "critical" for w in check_assignment(state, flight["id"], c["id"])):
            continue
        out.append(c)
    out.sort(key=lambda c: c["fatigue_score"])
    return out


def _find_recovery_crew(state: dict, flight: dict, statuses: tuple[str, ...]):
    """First legal crew member covering the flight's worst rank gap, or None."""
    for rank in _missing_ranks(state, flight):
        cands = _legal_candidates(state, flight, rank, statuses)
        if cands:
            return cands[0]
    return None


def _find_spare_aircraft(state: dict, flight: dict):
    """A same-type tail with no remaining active sector today, or None."""
    active = ("scheduled", "delayed", "boarding", "airborne")
    for ac in state.get("fleet", FLEET):
        if ac["type"] != flight["aircraft_type"] or ac["reg"] == flight["aircraft_reg"]:
            continue
        busy = any(
            f["aircraft_reg"] == ac["reg"] and f["status"] in active
            for f in state["flights"]
        )
        if not busy:
            return ac
    return None


def _cancellable_pairing_sectors(state: dict, flight: dict) -> list[dict]:
    """This flight plus any not-yet-departed sibling sectors in its pairing —
    cancelling the outbound cancels the crew's return too."""
    pairing_id = flight.get("pairing_id")
    sectors = [flight]
    for f in state["flights"]:
        if (pairing_id and f.get("pairing_id") == pairing_id and f["id"] != flight["id"]
                and f["status"] in ("scheduled", "delayed", "boarding")):
            sectors.append(f)
    return sectors


def _recovery_options_for(state: dict, flight: dict, kind: str, sev: str) -> list[dict]:
    """Build the decision menu for an incident from the CURRENT state of the
    operation: infeasible actions are flagged (with the reason), costs scale
    with pax count / sector length / severity, and feasible recovery options
    name the actual resource (crew member, spare tail) they would use."""
    pax = flight.get("pax_count", 0)
    block = flight.get("block_min", 0)
    sev_mult = 1.5 if sev == "major" else 1.0

    def opt(action, label, cost, otp_hit=0, fatigue=0, pax_disrupt=False,
            feasible=True, reason=None, detail=None):
        return {
            "action": action, "label": label, "cost_usd": int(cost),
            "otp_hit": otp_hit, "fatigue": fatigue, "pax_disrupt": pax_disrupt,
            "feasible": feasible, "reason": reason, "detail": detail,
        }

    cancel_sectors = _cancellable_pairing_sectors(state, flight)
    cancel_pax = sum(f.get("pax_count", 0) for f in cancel_sectors)
    base = [
        opt("delay", "Hold / Accept Delay", (1500 + pax * 12) * sev_mult, otp_hit=8, fatigue=2),
        opt(
            "cancel",
            "Cancel Flight" if len(cancel_sectors) == 1 else f"Cancel Pairing ({len(cancel_sectors)} sectors)",
            15000 * len(cancel_sectors) + cancel_pax * 280,
            pax_disrupt=True,
            detail=f"{cancel_pax} pax disrupted, crew released",
        ),
    ]

    if kind == "CREW_SICK":
        type_q = flight["required_crew"]["type_qual"]
        gaps = _missing_ranks(state, flight)
        gap_str = "/".join(gaps) if gaps else "crew"
        standby = _find_recovery_crew(state, flight, ("standby",))
        swap = _find_recovery_crew(state, flight, ("available",))
        return [
            opt("callout_standby", "Call Out Standby Crew",
                2500 + (2500 if block > 360 else 0), otp_hit=2, fatigue=5,
                feasible=standby is not None,
                reason=None if standby else f"No legal standby {gap_str} rated {type_q}",
                detail=f"{standby['id']} {standby['name']} ({standby['rank']})" if standby else None),
            opt("swap_crew", "Reassign Available Crew", 1200, otp_hit=4, fatigue=3,
                feasible=swap is not None,
                reason=None if swap else f"No legal available {gap_str} rated {type_q}",
                detail=f"{swap['id']} {swap['name']} ({swap['rank']})" if swap else None),
            opt("deadhead", "Position Crew (Deadhead)", 4000 + block * 3, otp_hit=12, fatigue=8),
            *base,
        ]
    if kind == "TECH":
        spare = _find_spare_aircraft(state, flight)
        return [
            opt("aircraft_swap", "Swap Aircraft From Spare", 8000 + pax * 15, otp_hit=18, fatigue=1,
                feasible=spare is not None,
                reason=None if spare else f"No spare {flight['aircraft_type']} on the ground",
                detail=spare["reg"] if spare else None),
            opt("mel_defer", "Accept MEL Deferral", 800, otp_hit=4,
                feasible=sev == "minor",
                reason=None if sev == "minor" else "Defect outside MEL limits — cannot defer"),
            *base,
        ]
    if kind == "WEATHER":
        return [
            opt("reroute", "Reroute / Alternate Airport", (6000 + pax * 35) * sev_mult,
                otp_hit=25, fatigue=4, pax_disrupt=True),
            *base,
        ]
    if kind == "ATC_FLOW":
        return [
            opt("request_slot", "Request Earlier CTOT Slot", 600, otp_hit=6),
            *base,
        ]
    if kind == "LATE_REPORT":
        return [
            opt("warn_crew", "Issue Verbal Warning", 0, otp_hit=2, fatigue=1),
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

    flight = next((f for f in state["flights"] if f["id"] == inc["flight_id"]), None)

    # ---- Validate BEFORE charging: the world may have moved on since the
    # options were generated, so feasibility is re-checked live. On failure the
    # incident stays open and nothing is paid.
    replacement = None
    spare = None
    if flight:
        if action == "callout_standby":
            replacement = _find_recovery_crew(state, flight, ("standby",))
            if not replacement:
                return {"ok": False, "incident": inc,
                        "reason": chosen.get("reason") or
                        f"No legal standby crew rated {flight['required_crew']['type_qual']} available."}
        elif action == "swap_crew":
            replacement = _find_recovery_crew(state, flight, ("available",))
            if not replacement:
                return {"ok": False, "incident": inc,
                        "reason": chosen.get("reason") or
                        f"No legal available crew rated {flight['required_crew']['type_qual']}."}
        elif action == "aircraft_swap":
            spare = _find_spare_aircraft(state, flight)
            if not spare:
                return {"ok": False, "incident": inc,
                        "reason": f"No spare {flight['aircraft_type']} on the ground."}
        elif chosen.get("feasible") is False:
            return {"ok": False, "incident": inc,
                    "reason": chosen.get("reason") or "Option not feasible."}

    # ---- Apply (success guaranteed from here)
    cost = chosen.get("cost_usd", 0)
    otp_hit = chosen.get("otp_hit", 0)
    fatigue = chosen.get("fatigue", 0)
    pax_disrupt = chosen.get("pax_disrupt", False)

    state["kpis"]["cost_usd"] += cost
    state["kpis"]["fatigue_index"] = min(100, state["kpis"]["fatigue_index"] + fatigue)
    if flight:
        if action == "cancel":
            # Cancelling the outbound kills the rest of the pairing too, and
            # releases the rostered crew back to the pool.
            to_cancel = _cancellable_pairing_sectors(state, flight)
            released: set[str] = set()
            for cf in to_cancel:
                cf["status"] = "cancelled"
                state["kpis"]["pax_disrupted"] += cf.get("pax_count", 0)
                state["kpis"]["pax_delay_min"] += 240 * cf.get("pax_count", 0)
                for cid in list(cf["assigned_crew_ids"]):
                    cf["assigned_crew_ids"].remove(cid)
                    released.add(cid)
            for cid in released:
                c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
                if c and not any(cid in f["assigned_crew_ids"] for f in state["flights"]):
                    c["assigned_flight_id"] = None
                    if c["status"] == "on_duty":
                        c["status"] = "available"
            if len(to_cancel) > 1 or released:
                inc["resolution_note"] = (
                    f"{len(to_cancel)} sector(s) cancelled; "
                    f"{len(released)} crew released to the pool."
                )
        elif action in ("callout_standby", "swap_crew"):
            # assign_crew handles the whole pairing + legality bookkeeping
            assign_crew(state, flight["id"], replacement["id"])
            replacement["status"] = "on_duty"
            inc["replacement_crew_id"] = replacement["id"]
            inc["replacement_crew_name"] = replacement["name"]
            if action == "swap_crew":
                flight["delay_min"] += 20
        elif action == "aircraft_swap":
            # the spare tail takes over every remaining sector of the pairing
            pairing_id = flight.get("pairing_id")
            for pf in state["flights"]:
                same_pairing = pf["id"] == flight["id"] or (pairing_id and pf.get("pairing_id") == pairing_id)
                if same_pairing and pf["status"] in ("scheduled", "delayed", "boarding"):
                    pf["aircraft_reg"] = spare["reg"]
            inc["resolution_note"] = f"Aircraft swapped to {spare['reg']}."
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
    reactionary = propagate_reactionary_delays(state)
    _recompute_kpis(state)
    return {
        "ok": True,
        "incident": inc,
        "kpis": state["kpis"],
        "reactionary_delays": reactionary,
    }


def propagate_reactionary_delays(state: dict) -> list[dict]:
    """Roll knock-on (reactionary) delays down each aircraft's day.

    For every tail, walk its sectors in schedule order tracking when the
    aircraft is actually ready again (estimated arrival + minimum turnaround).
    Any later sector that would depart before its aircraft is ready picks up
    the difference as reactionary delay. Re-running is safe: applied delay
    feeds back into the effective departure time, so a sector is only pushed
    further if its inbound slipped further since the last pass.
    """
    affected: list[dict] = []
    by_reg: dict[str, list[dict]] = {}
    for f in state["flights"]:
        by_reg.setdefault(f["aircraft_reg"], []).append(f)

    for _reg, sectors in by_reg.items():
        sectors.sort(key=lambda f: f["std"])
        ready_at: datetime | None = None
        inbound: dict | None = None
        for f in sectors:
            if f["status"] == "cancelled":
                # Sector never flies; the tail stays wherever it was.
                continue
            std = datetime.fromisoformat(f["std"])
            eff_dep = std + timedelta(minutes=f.get("delay_min", 0))
            if (
                ready_at is not None
                and eff_dep < ready_at
                and f["status"] in ("scheduled", "delayed", "boarding")
            ):
                extra = int((ready_at - eff_dep).total_seconds() // 60)
                if extra > 0:
                    f["delay_min"] += extra
                    f["reactionary_min"] = f.get("reactionary_min", 0) + extra
                    if f["status"] == "scheduled":
                        f["status"] = "delayed"
                    note = f.get("note") or ""
                    if not note or note.startswith("REACTIONARY"):
                        f["note"] = (
                            f"REACTIONARY (IATA 93) · inbound {inbound['callsign']} late"
                            if inbound else "REACTIONARY (IATA 93) · aircraft late"
                        )
                    affected.append({
                        "flight_id": f["id"],
                        "callsign": f["callsign"],
                        "added_min": extra,
                        "inbound_callsign": inbound["callsign"] if inbound else None,
                    })
                    eff_dep = std + timedelta(minutes=f["delay_min"])
            eff_arr = eff_dep + timedelta(minutes=f["block_min"])
            turnaround = MIN_TURNAROUND_MIN + (
                DIVERSION_RECOVERY_MIN if f["status"] == "diverted" else 0
            )
            ready_at = eff_arr + timedelta(minutes=turnaround)
            inbound = f
    return affected


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


def restart_day(state: dict) -> dict:
    """Reset the current day to its start: clock back to 04:00Z, incidents
    cleared, decisions wiped, flight delays/status reset, KPIs reset to fresh.
    The roster (crew assignments to flights) is preserved.
    """
    state["clock"] = state["day_start"]
    state["incidents"] = []
    state["decisions_log"] = []
    state["tick_count"] = 0
    state["phase"] = "OPS"
    state["kpis"] = {
        "otp_pct": 100.0,
        "legality_breaches": 0,
        "curfew_violations": 0,
        "compensation_usd": 0,
        "fatigue_index": int(sum(c["fatigue_score"] for c in state["crew"]) / max(1, len(state["crew"]))),
        "cost_usd": 0,
        "pax_delay_min": 0,
        "pax_disrupted": 0,
        "score": 1000,
    }
    # Reset flight runtime fields, keep crew assignments
    for f in state["flights"]:
        f["status"] = "scheduled"
        f["delay_min"] = 0
        f["reactionary_min"] = 0
        # One-shot per-day flags must re-arm on a restart (the curfew-checked
        # flags previously survived restarts, so a restarted day was never
        # curfew-checked again — latent bug fixed alongside the comp flags)
        f.pop("curfew_dep_checked", None)
        f.pop("curfew_arr_checked", None)
        f.pop("curfew_violation", None)
        f.pop("comp_charged", None)
        f.pop("comp_exempt", None)
        # Don't clobber the night-stop return note
        if not (f.get("note") or "").startswith("RETURN FROM NIGHT-STOP"):
            f["note"] = ""
    # Restore any sick crew that became sick during this day's ops back to on-duty
    # Cleanest approach: if a crew was assigned to any flight, they're on_duty again
    assigned_ids = {cid for f in state["flights"] for cid in f["assigned_crew_ids"]}
    for c in state["crew"]:
        c["fdp_used_min"] = 0  # reset FDP accumulation for the fresh restart
        if c["id"] in assigned_ids:
            c["status"] = "on_duty"
            # Make sure assigned_flight_id is set to one of the assigned flights
            c["assigned_flight_id"] = next(
                (f["id"] for f in state["flights"] if c["id"] in f["assigned_crew_ids"]),
                None,
            )
        elif c["status"] == "sick":
            # Crew that called in sick AT DAY START stay sick; this is a coarse approximation
            pass
    return {"ok": True, "clock": state["clock"]}


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
